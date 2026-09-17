from pythonosc.udp_client import SimpleUDPClient
from threading import Event, RLock
import ctypes
import logging
import os
import socket
import time

from Controllers.DataController import ConfigSettings, Leash

logger = logging.getLogger(__name__)


class Program:
    def __init__(self):
        self.stateLock = RLock()
        self.wake = Event()
        self.stopped = Event()
        self.activeLeash = None
        self._client = None
        self._resetPending = False

    def resetLeashes(self, leashes):
        with self.stateLock:
            for leash in leashes:
                leash.Grabbed = False
                leash.Active = False
                leash.Stretch = 0.0
                leash.resetMovement()
            self._resetPending = True
        self.wake.set()

    def run(self, leashes, checkConnection=None):
        settings = leashes[0].settings
        try:
            if not settings.XboxJoystickMovement:
                self._client = SimpleUDPClient(settings.IP, settings.SendingPort, family=socket.AF_INET)
            self.stopMovement(settings)
            while not self.stopped.is_set():
                self.wake.clear()
                self.updateMovement(leashes)
                if checkConnection is not None:
                    checkConnection()
                delay = settings.ActiveDelay if self.activeLeash else settings.InactiveDelay
                self.wake.wait(delay)
        finally:
            try:
                self.stopMovement(settings)
            finally:
                if self._client is not None:
                    self._client.close()
                    self._client = None

    def stop(self):
        self.stopped.set()
        self.wake.set()

    def updateMovement(self, leashes):
        # The receiver uses the same lock, so each output uses a consistent snapshot.
        with self.stateLock:
            if self._resetPending:
                self.stopMovement(leashes[0].settings)
                self.activeLeash = None
                self._resetPending = False
            previous = self.activeLeash
            if previous is not None and not previous.Grabbed:
                logger.info("%s dropped", previous.Name)
                previous.Active = False
                self.stopMovement(previous.settings)
                self.activeLeash = None
            if self.activeLeash is None:
                self.activeLeash = next((leash for leash in leashes if leash.Grabbed), None)
                if self.activeLeash is not None:
                    self.activeLeash.Active = True
                    logger.info("%s grabbed", self.activeLeash.Name)
            if self.activeLeash is None:
                return

            leash = self.activeLeash
            if leash.settings.Logging:
                leash.printDirections()
            vert, hori, turn, run = self.movement(leash)
            self.leashOutput(vert, hori, turn, run, leash.settings)

    def movement(self, leash):
        #Movement Math
        outputMultiplier = leash.Stretch * leash.settings.StrengthMultiplier
        VerticalOutput = self.clamp((leash.Z_Positive - leash.Z_Negative) * outputMultiplier)
        HorizontalOutput = self.clamp((leash.X_Positive - leash.X_Negative) * outputMultiplier)

        Y_Combined = leash.Y_Positive + leash.Y_Negative
        #Up/Down Deadzone, stops movement if pulled too high or low.
        if leash.settings.UpDownDeadzone < 1 and Y_Combined >= leash.settings.UpDownDeadzone:
            VerticalOutput = 0.0
            HorizontalOutput = 0.0
            
        #Up/Down Compensation
        if leash.settings.UpDownCompensation != 0:
            Y_Modifier = max(0.0001, 1.0 - Y_Combined * leash.settings.UpDownCompensation)
            VerticalOutput /= Y_Modifier
            HorizontalOutput /= Y_Modifier

        #Turning Math
        if leash.settings.TurningEnabled and leash.Stretch > leash.settings.TurningDeadzone:
            TurningSpeed = leash.settings.TurningMultiplier

            match leash.LeashDirection:
                case "North":
                    if leash.Z_Positive < leash.settings.TurningGoal:
                        TurningSpeed *= HorizontalOutput
                        if leash.X_Positive > leash.X_Negative:
                            # Right
                            TurningSpeed += leash.Z_Negative
                        else: 
                            # Left
                            TurningSpeed -= leash.Z_Negative
                    else: 
                        TurningSpeed = 0.0
                case "South":
                    if leash.Z_Negative < leash.settings.TurningGoal:
                        TurningSpeed *= -HorizontalOutput
                        if leash.X_Positive > leash.X_Negative:
                            # Left
                            TurningSpeed -= leash.Z_Positive
                        else:
                            # Right
                            TurningSpeed += leash.Z_Positive
                    else:
                        TurningSpeed = 0.0
                case "East":
                    if leash.X_Positive < leash.settings.TurningGoal:
                        TurningSpeed *= VerticalOutput
                        if leash.Z_Positive > leash.Z_Negative:
                            # Right
                            TurningSpeed += leash.X_Negative
                        else:
                            # Left
                            TurningSpeed -= leash.X_Negative
                    else:   
                        TurningSpeed = 0.0
                case "West":
                    if leash.X_Negative < leash.settings.TurningGoal:
                        TurningSpeed *= -VerticalOutput
                        if leash.Z_Positive > leash.Z_Negative:
                            # Left
                            TurningSpeed -= leash.X_Positive
                        else:
                            # Right
                            TurningSpeed += leash.X_Positive
                    else:
                        TurningSpeed = 0.0

                case _:
                    TurningSpeed = 0.0

            TurningSpeed = self.clamp(TurningSpeed)
        else:
            TurningSpeed = 0.0

        if not leash.Grabbed or leash.Stretch <= leash.settings.WalkDeadzone:
            return 0.0, 0.0, 0.0, 0
        return (self.clamp(VerticalOutput), self.clamp(HorizontalOutput),
                TurningSpeed, int(leash.Stretch > leash.settings.RunDeadzone))

    def stopMovement(self, settings):
        # Repeat the release because UDP does not guarantee delivery.
        for attempt in range(2):
            try:
                self.leashOutput(0.0, 0.0, 0.0, 0, settings)
            except OSError:
                logger.exception("Could not send movement reset to %s:%s", settings.IP, settings.SendingPort)
            if attempt == 0:
                time.sleep(settings.ActiveDelay)

    def leashOutput(self, vert: float, hori: float, turn: float, runType: int, settings: ConfigSettings):
        vert, hori, turn = (float(self.clamp(value)) for value in (vert, hori, turn))
        if settings.XboxJoystickMovement:
            settings.gamepad.left_joystick_float(x_value_float=hori, y_value_float=vert)
            if settings.TurningEnabled:
                settings.gamepad.right_joystick_float(x_value_float=turn, y_value_float=0.0)
            if runType:
                settings.gamepad.press_button(button=settings.runButton)
            else:
                settings.gamepad.release_button(button=settings.runButton)
            settings.gamepad.update()
            logger.debug("Gamepad output: vertical=%.3f horizontal=%.3f turn=%.3f run=%d",
                         vert, hori, turn, runType)
            return

        if self._client is None:
            self._client = SimpleUDPClient(settings.IP, settings.SendingPort, family=socket.AF_INET)
        messages = [("/input/Vertical", vert), ("/input/Horizontal", hori)]
        if settings.TurningEnabled:
            messages.append(("/input/LookHorizontal", turn))
        messages.append(("/input/Run", int(runType)))
        for address, value in messages:
            self._client.send_message(address, value)
            logger.debug("OSC TX %s:%s %s %r", settings.IP, settings.SendingPort, address, value)

    @staticmethod
    def clamp(n):
        return max(-1.0, min(n, 1.0))

    @staticmethod
    def setWindowTitle():
        if os.name == 'nt':
            ctypes.windll.kernel32.SetConsoleTitleW("OSCLeash")
