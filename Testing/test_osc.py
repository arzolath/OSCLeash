import io
import json
import logging
import os
from pathlib import Path
import socket
import tempfile
from threading import Thread
import time
import unittest
from unittest.mock import Mock, patch
from urllib.request import urlopen

from pythonosc.osc_bundle_builder import IMMEDIATELY, OscBundleBuilder
from pythonosc.osc_message import OscMessage
from pythonosc.osc_message_builder import OscMessageBuilder
from pythonosc.udp_client import SimpleUDPClient

from Controllers.DataController import ConfigSettings, DefaultConfig, Leash
from Controllers.PackageController import Package
from Controllers.ThreadController import Program
from OSCLeash import configFilePath, configureLogging, createDefaultConfigFile, main


def makeLeashes(**config):
    settings = ConfigSettings(config)
    return [Leash(name, settings.DirectionalParameters, settings) for name in settings.Leashes]


class ConfigTests(unittest.TestCase):
    def test_old_config_preserves_custom_settings_and_adds_defaults(self):
        settings = ConfigSettings({"IP": "192.0.2.10", "StrengthMultiplier": 2,
                                   "DirectionalParameters": {"Z_Positive_Param": "CustomZ"}})
        self.assertEqual(settings.IP, "192.0.2.10")
        self.assertEqual(settings.BindIP, "127.0.0.1")
        self.assertEqual(settings.StrengthMultiplier, 2)
        self.assertFalse(settings.VerboseLogging)
        self.assertEqual(settings.DirectionalParameters['Z_Positive_Param'], 'CustomZ')
        self.assertEqual(DefaultConfig['DirectionalParameters']['Z_Positive_Param'], 'Leash_Z+')

    def test_invalid_settings_fail_with_useful_errors(self):
        cases = [("ListeningPort", True), ("SendingPort", 65536), ("ActiveDelay", 0),
                 ("InactiveDelay", -1), ("VerboseLogging", "false"),
                 ("StrengthMultiplier", float('nan')), ("RunDeadzone", 2),
                 ("PhysboneParameters", []), ("PhysboneParameters", ["Leash", "Leash"]),
                 ("DirectionalParameters", None)]
        for key, value in cases:
            with self.subTest(key=key, value=value), self.assertRaisesRegex(ValueError, key):
                ConfigSettings({key: value})

    def test_relative_config_override_and_creation(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            configPath = Path(directory) / 'config.json'
            relative = os.path.relpath(configPath)
            with patch.dict(os.environ, {'OSCLEASH_CONFIG_PATH': relative}):
                self.assertEqual(configFilePath(), configPath.resolve())
                createDefaultConfigFile(relative)
            self.assertEqual(json.loads(configPath.read_text()), DefaultConfig)
            with self.assertRaises(FileExistsError):
                createDefaultConfigFile(configPath)

    def test_malformed_config_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            configPath = Path(directory) / 'config.json'
            configPath.write_text('{broken')
            with patch.dict(os.environ, {'OSCLEASH_CONFIG_PATH': str(configPath)}), \
                    patch('OSCLeash.configureLogging'), self.assertLogs(level='ERROR'):
                self.assertEqual(main(), 1)
            self.assertEqual(configPath.read_text(), '{broken')

    def test_repository_config_matches_defaults(self):
        configPath = Path(__file__).resolve().parents[1] / 'Config.json'
        self.assertEqual(json.loads(configPath.read_text()), DefaultConfig)

    def test_verbose_console_logging_is_optional(self):
        root = logging.getLogger()
        oldHandlers, oldLevel = root.handlers[:], root.level
        try:
            for verbose in (False, True):
                with self.subTest(verbose=verbose), patch('sys.stdout', new_callable=io.StringIO) as output:
                    configureLogging(verbose)
                    logging.getLogger('Controllers.PackageController').debug('packet detail')
                    logging.getLogger('Controllers.PackageController').info('receiver started')
                    self.assertIn('receiver started', output.getvalue())
                    self.assertEqual('packet detail' in output.getvalue(), verbose)
        finally:
            root.handlers = oldHandlers
            root.setLevel(oldLevel)


class MovementTests(unittest.TestCase):
    def setUp(self):
        self.program = Program()
        self.program.leashOutput = Mock()
        self.leashes = makeLeashes(ActiveDelay=0.001)
        self.leash = self.leashes[0]
        self.leash.Grabbed = True
        self.leash.Stretch = 0.8
        self.leash.Z_Positive = 0.7

    def test_release_stops_with_logging_disabled(self):
        self.program.updateMovement(self.leashes)
        self.assertGreater(self.program.leashOutput.call_args.args[0], 0)
        self.leash.Grabbed = False
        self.program.leashOutput.reset_mock()
        self.program.updateMovement(self.leashes)
        self.assertEqual(self.program.leashOutput.call_count, 2)
        self.assertEqual(self.program.leashOutput.call_args.args[:4], (0.0, 0.0, 0.0, 0))
        self.assertIsNone(self.program.activeLeash)
        # VRChat only sends changes; releasing must not discard the compass values.
        self.assertEqual(self.leash.Z_Positive, 0.7)

    def test_second_grabbed_leash_takes_over_without_another_grab_message(self):
        second = Leash('Second', self.leash.settings.DirectionalParameters, self.leash.settings)
        second.Grabbed = True
        leashes = self.leashes + [second]
        self.program.updateMovement(leashes)
        self.assertIs(self.program.activeLeash, self.leash)
        self.leash.Grabbed = False
        self.program.updateMovement(leashes)
        self.assertIs(self.program.activeLeash, second)

    def test_compensation_clamps_and_does_not_reverse_movement(self):
        self.leash.settings.UpDownDeadzone = 1
        self.leash.Y_Positive = 0.8
        for compensation in (1, 2):
            self.leash.settings.UpDownCompensation = compensation
            self.assertEqual(self.program.movement(self.leash)[0], 1.0)

    def test_deadzone_one_disables_vertical_cutoff(self):
        self.leash.Y_Positive = 1
        self.assertEqual(self.program.movement(self.leash)[0], 0)
        self.leash.settings.UpDownDeadzone = 1
        self.assertEqual(self.program.movement(self.leash)[0], 1)

    def test_unknown_turning_direction_does_not_spin(self):
        with self.assertLogs(level='WARNING'):
            leash = makeLeashes(TurningEnabled=True)[0]
        leash.Grabbed, leash.Stretch = True, 1
        self.assertEqual(self.program.movement(leash)[2], 0)

    def test_turning_directions(self):
        for direction, axis, expected in [('North', 'X_Positive', 0.8),
                                          ('South', 'X_Positive', -0.8),
                                          ('East', 'Z_Positive', 0.8),
                                          ('West', 'Z_Positive', -0.8)]:
            with self.subTest(direction=direction):
                leash = makeLeashes(TurningEnabled=True, StrengthMultiplier=1,
                                    PhysboneParameters=[f'Leash_{direction}'])[0]
                leash.Grabbed, leash.Stretch = True, 1
                setattr(leash, axis, 1)
                self.assertEqual(self.program.movement(leash)[2], expected)

    def test_gamepad_release_does_not_create_osc_client(self):
        settings = self.leash.settings
        settings.XboxJoystickMovement = True
        settings.addGamepadControls(Mock(), 'shoulder')
        program = Program()
        with patch('Controllers.ThreadController.SimpleUDPClient') as client:
            program.leashOutput(2.0, -2.0, 0, 1, settings)
            settings.gamepad.left_joystick_float.assert_called_with(x_value_float=-1.0, y_value_float=1.0)
            settings.gamepad.press_button.assert_called_with(button='shoulder')
            program.stopMovement(settings)
            settings.gamepad.left_joystick_float.assert_called_with(x_value_float=0.0, y_value_float=0.0)
            settings.gamepad.release_button.assert_called_with(button='shoulder')
            client.assert_not_called()

    def test_avatar_change_clears_state_and_sends_stop(self):
        self.program.updateMovement(self.leashes)
        self.program.resetLeashes(self.leashes)
        self.program.updateMovement(self.leashes)
        self.assertFalse(self.leash.Grabbed)
        self.assertFalse(self.leash.Active)
        self.assertEqual(self.leash.Z_Positive, 0)
        self.assertEqual(self.program.leashOutput.call_args.args[:4], (0, 0, 0, 0))

    def test_worker_exception_still_sends_stop(self):
        self.program.updateMovement = Mock(side_effect=RuntimeError('test failure'))
        with self.assertRaisesRegex(RuntimeError, 'test failure'):
            self.program.run(self.leashes)
        self.assertEqual(self.program.leashOutput.call_args.args[:4], (0, 0, 0, 0))


class ReceiverTests(unittest.TestCase):
    def setUp(self):
        self.leashes = makeLeashes(ActiveDelay=0.001)
        self.package = Package(self.leashes, False)
        self.package.listen()
        self.package.start('127.0.0.1', 0)
        self.addCleanup(self.package.close)
        self.client = SimpleUDPClient('127.0.0.1', self.package.server.server_address[1])
        self.addCleanup(self.client.close)

    def waitFor(self, predicate):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            with self.package.program.stateLock:
                if predicate():
                    return
            time.sleep(0.005)
        self.fail('Timed out waiting for OSC receiver')

    def sendBundle(self, messages):
        bundle = OscBundleBuilder(IMMEDIATELY)
        for address, value in messages:
            message = OscMessageBuilder(address=address)
            message.add_arg(value)
            bundle.add_content(message.build())
        self.client.send(bundle.build())

    def test_real_udp_bundle_updates_leash(self):
        self.sendBundle([('/avatar/parameters/Leash_Z+', 0.5),
                         ('/avatar/parameters/Leash_Stretch', 0.75),
                         ('/avatar/parameters/Leash_IsGrabbed', True)])
        self.waitFor(lambda: self.leashes[0].Grabbed)
        self.assertEqual(self.leashes[0].Stretch, 0.75)
        self.assertEqual(self.leashes[0].Z_Positive, 0.5)

    def test_invalid_messages_do_not_kill_receiver_or_change_state(self):
        for value in ('bad', float('nan'), float('inf'), -1, 2, True):
            self.client.send_message('/avatar/parameters/Leash_Stretch', value)
        self.client.send_message('/avatar/parameters/Leash_IsGrabbed', 'false')
        self.client.send_message('/avatar/parameters/Leash_IsGrabbed', [])
        self.client.send_message('/avatar/parameters/Leash_IsGrabbed', [True, False])
        self.client.send_message('/avatar/parameters/Leash_Z+', 0.25)
        self.waitFor(lambda: self.leashes[0].Z_Positive == 0.25)
        self.assertEqual(self.leashes[0].Stretch, 0)
        self.assertFalse(self.leashes[0].Grabbed)

    def test_port_conflict_is_reported_to_caller(self):
        other = Package(self.leashes, False)
        self.addCleanup(other.close)
        with self.assertRaisesRegex(OSError, 'Cannot listen'):
            other.start('127.0.0.1', self.package.server.server_address[1])

    def test_diagnostics_distinguish_missing_traffic_from_unmapped_parameters(self):
        self.package._lastDiagnostic -= 11
        with self.assertLogs(level='WARNING') as logs:
            self.package.checkConnection()
        self.assertIn('No OSC messages received', logs.output[0])
        self.client.send_message('/avatar/parameters/Other', 1)
        self.waitFor(lambda: self.package._received == 1)
        self.package._diagnosed = False
        self.package._lastDiagnostic -= 11
        with self.assertLogs(level='WARNING') as logs:
            self.package.checkConnection()
        self.assertIn('no valid leash parameters matched', logs.output[0])

    def test_end_to_end_movement_release_and_shutdown(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as output:
            output.bind(('127.0.0.1', 0))
            output.settimeout(2)
            self.leashes[0].settings.SendingPort = output.getsockname()[1]
            worker = Thread(target=self.package.program.run, args=(self.leashes,))
            worker.start()
            try:
                self.sendBundle([('/avatar/parameters/Leash_Z+', 1.0),
                                 ('/avatar/parameters/Leash_Stretch', 0.8),
                                 ('/avatar/parameters/Leash_IsGrabbed', True)])
                messages = self.readThrough(output, '/input/Run', 1)
                vertical = [m for m in messages if m.address == '/input/Vertical'][-1]
                self.assertIs(type(vertical.params[0]), float)
                self.assertGreater(vertical.params[0], 0)
                self.assertIs(type(messages[-1].params[0]), int)
                self.client.send_message('/avatar/parameters/Leash_IsGrabbed', False)
                stopped = self.readThrough(output, '/input/Run', 0)
                self.assertEqual(stopped[-3].params, [0.0])
                self.assertEqual(stopped[-2].params, [0.0])
            finally:
                self.package.program.stop()
                worker.join(2)
            self.assertFalse(worker.is_alive())
            # Drain any release retries and verify shutdown's final output is neutral.
            output.settimeout(0.1)
            remaining = []
            try:
                while True:
                    remaining.append(OscMessage(output.recv(4096)))
            except socket.timeout:
                pass
            self.assertGreaterEqual(len(remaining), 6)
            self.assertTrue(all(message.params == [0] for message in remaining[-6:]))

    def readThrough(self, sock, address, value):
        messages = []
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            message = OscMessage(sock.recv(4096))
            messages.append(message)
            if message.address == address and message.params == [value]:
                return messages
        self.fail('Expected OSC output was not received')


class QueryTests(unittest.TestCase):
    def test_query_tree_is_available_when_advertised_and_uses_bound_udp_port(self):
        package = Package(makeLeashes(), True)
        package.listen()
        self.addCleanup(package.close)
        registrations = []

        def inspectAdvertisement(info):
            registrations.append(info)
            service = package._oscQueryService
            with urlopen(f'http://127.0.0.1:{service.httpPort}/?HOST_INFO', timeout=2) as response:
                host = json.load(response)
            self.assertEqual(host['OSC_PORT'], package.server.server_address[1])
            with urlopen(f'http://127.0.0.1:{service.httpPort}/avatar', timeout=2) as response:
                avatar = json.load(response)
            self.assertEqual(avatar['CONTENTS']['change']['TYPE'], 's')
            parameters = avatar['CONTENTS']['parameters']['CONTENTS']
            self.assertEqual(parameters['Leash_Stretch']['TYPE'], 'f')
            self.assertEqual(parameters['Leash_IsGrabbed']['ACCESS'], 2)

        with patch('Controllers.QueryController.Zeroconf') as zeroconf:
            zeroconf.return_value.register_service.side_effect = inspectAdvertisement
            package.start('127.0.0.1', 9001)
            self.assertEqual(len(registrations), 2)
            self.assertEqual(registrations[1].port, package.server.server_address[1])
            service = package._oscQueryService
            package.close()
            self.assertFalse(service._thread.is_alive())
            zeroconf.return_value.unregister_all_services.assert_called_once()
            zeroconf.return_value.close.assert_called_once()

    def test_query_failure_releases_udp_port(self):
        package = Package(makeLeashes(), True)
        package.listen()
        self.addCleanup(package.close)
        with patch('Controllers.QueryController.Zeroconf', side_effect=OSError('mDNS unavailable')):
            with self.assertRaisesRegex(OSError, 'mDNS unavailable'):
                package.start('127.0.0.1', 9001)
        self.assertIsNone(package.server)

    def test_query_rejects_unsupported_bind_address(self):
        package = Package(makeLeashes(), True)
        with self.assertRaisesRegex(ValueError, 'fixed ports for LAN'):
            package.start('0.0.0.0', 9001)


if __name__ == '__main__':
    unittest.main()
