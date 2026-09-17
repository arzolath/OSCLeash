#!/usr/bin/env python3
import json
import logging
import os
from pathlib import Path
import sys

from Controllers.DataController import DefaultConfig, ConfigSettings, Leash
from Controllers.PackageController import Package
from Controllers.ThreadController import Program

# Replaced by the release build.
__version__ = "v" + "VERSION_PLACEHOLDER"
logger = logging.getLogger(__name__)


def configFilePath():
    override = os.environ.get('OSCLEASH_CONFIG_PATH')
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == 'win32':
        base = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local')
        return base / 'Programs' / 'OSCLeash' / 'Config.json'
    base = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config')
    return base / 'OSCLeash' / 'Config.json'


def createDefaultConfigFile(configPath):
    path = Path(configPath)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as configFile:
        json.dump(DefaultConfig, configFile, indent=4)
        configFile.write('\n')
    logger.info("Created default config at %s", path)


def configureLogging(verbose=False):
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s', datefmt='%H:%M:%S',
                        stream=sys.stdout, force=True)
    for name in ('zeroconf', 'asyncio', 'urllib3'):
        logging.getLogger(name).setLevel(logging.WARNING)


def main():
    configureLogging()
    program = Program()
    program.setWindowTitle()
    version = '(Local Build)' if 'PLACEHOLDER' in __version__ else __version__
    logger.info("OSCLeash %s", version)
    package = None
    try:
        configPath = configFilePath()
        logger.info("Config: %s", configPath)
        if not configPath.is_file():
            createDefaultConfigFile(configPath)
        with configPath.open(encoding='utf-8-sig') as configFile:
            configData = json.load(configFile)
        settings = ConfigSettings(configData)
        configureLogging(settings.VerboseLogging)
        settings.printInfo()

        if settings.XboxJoystickMovement:
            try:
                import vgamepad as vg
                settings.addGamepadControls(vg.VX360Gamepad(), vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER)
            except Exception as exc:
                logger.warning("Gamepad initialization failed: %s. Using OSC movement.", exc)
                settings.XboxJoystickMovement = False

        leashes = [Leash(name, settings.DirectionalParameters, settings) for name in settings.Leashes]
        package = Package(leashes, settings.UseOSCQuery, program)
        package.listen()
        package.start(settings.BindIP, settings.ListeningPort)
        logger.info("Started, awaiting input. Press Ctrl+C to stop.")
        program.run(leashes, package.checkConnection)
        return 0
    except KeyboardInterrupt:
        logger.info("Stopping OSCLeash")
        return 0
    except Exception as exc:
        logger.error("OSCLeash could not continue: %s", exc, exc_info=logger.isEnabledFor(logging.DEBUG))
        return 1
    finally:
        program.stop()
        if package is not None:
            package.close()


if __name__ == '__main__':
    sys.exit(main())
