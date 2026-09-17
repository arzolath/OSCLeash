from copy import deepcopy
import logging
import math

logger = logging.getLogger(__name__)

DefaultConfig = {
        "IP": "127.0.0.1",
        "BindIP": "127.0.0.1",
        "ListeningPort": 9001,
        "SendingPort": 9000,
        "RunDeadzone": 0.70,
        "WalkDeadzone": 0.15,
        "StrengthMultiplier": 1.2,
        "UpDownCompensation": 1.0,
        "UpDownDeadzone": 0.5,
        "TurningEnabled": False,
        "TurningMultiplier": 0.80,
        "TurningDeadzone": 0.15,
        "TurningGoal": 90,
        "ActiveDelay": 0.02,
        "InactiveDelay": 0.5,
        "Logging": False,
        "VerboseLogging": False,
        "XboxJoystickMovement": False,
        "UseOSCQuery": False,
        
        "PhysboneParameters":
        [
                "Leash"
        ],
        "DirectionalParameters":
        {
                "Z_Positive_Param": "Leash_Z+",
                "Z_Negative_Param": "Leash_Z-",
                "X_Positive_Param": "Leash_X+",
                "X_Negative_Param": "Leash_X-",
                "Y_Positive_Param": "Leash_Y+",
                "Y_Negative_Param": "Leash_Y-"
        }
}


class ConfigSettings:

    def __init__(self, configData):
        self.setSettings(configData)

    def setSettings(self, configJson):
        if not isinstance(configJson, dict):
            raise ValueError("Config.json must contain a JSON object")

        config = deepcopy(DefaultConfig)
        config.update(configJson)
        contacts = configJson.get("DirectionalParameters", {})
        if not isinstance(contacts, dict):
            raise ValueError("DirectionalParameters must be an object")
        config["DirectionalParameters"] = {
            **DefaultConfig["DirectionalParameters"], **contacts
        }

        for key in configJson.keys() - DefaultConfig.keys():
            logger.warning("Unknown config setting %r; check its spelling and capitalization", key)
        for key in ("IP", "BindIP"):
            if not isinstance(config[key], str) or not config[key].strip():
                raise ValueError(f"{key} must be an IP address or hostname")
        for key in ("ListeningPort", "SendingPort"):
            if type(config[key]) is not int or not 1 <= config[key] <= 65535:
                raise ValueError(f"{key} must be an integer between 1 and 65535")
        for key in ("Logging", "VerboseLogging", "TurningEnabled",
                    "XboxJoystickMovement", "UseOSCQuery"):
            if type(config[key]) is not bool:
                raise ValueError(f"{key} must be true or false")
        for key in ("RunDeadzone", "WalkDeadzone", "StrengthMultiplier",
                    "UpDownCompensation", "UpDownDeadzone", "TurningMultiplier",
                    "TurningDeadzone", "TurningGoal", "ActiveDelay", "InactiveDelay"):
            value = config[key]
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError(f"{key} must be a finite, non-negative number")
        for key in ("ActiveDelay", "InactiveDelay"):
            if config[key] == 0:
                raise ValueError(f"{key} must be greater than zero")
        for key in ("RunDeadzone", "WalkDeadzone", "TurningDeadzone", "UpDownDeadzone"):
            if config[key] > 1:
                raise ValueError(f"{key} must be between 0 and 1")
        if config["WalkDeadzone"] > config["RunDeadzone"]:
            raise ValueError("WalkDeadzone cannot exceed RunDeadzone")
        if config["TurningGoal"] > 144:
            raise ValueError("TurningGoal must be between 0 and 144 degrees")

        leashes = config["PhysboneParameters"]
        if not isinstance(leashes, list) or not leashes:
            raise ValueError("PhysboneParameters must be a non-empty list")
        names = leashes + list(config["DirectionalParameters"].values())
        for name in names:
            if (not isinstance(name, str) or not name.strip()
                    or any(c.isspace() or c in '*?[],{}#\\\0' for c in name)):
                raise ValueError(f"Invalid OSC parameter name: {name!r}")
        if len(set(leashes)) != len(leashes):
            raise ValueError("PhysboneParameters contains duplicate names")
        addresses = [f"{name}_{suffix}" for name in leashes
                     for suffix in ("Stretch", "IsGrabbed")]
        addresses.extend(config["DirectionalParameters"].values())
        if len(set(addresses)) != len(addresses):
            raise ValueError("Leash and directional parameter names must be distinct")

        self.config = config
        for key in DefaultConfig:
            setattr(self, key, config[key])
        self.Leashes = config["PhysboneParameters"]
        self.TurningGoal = config["TurningGoal"] / 180

    def addGamepadControls(self, gamepad, runButton):
        self.gamepad = gamepad
        self.runButton = runButton

    def printInfo(self):
        logger.info("Sending OSC to %s:%s", self.IP, self.SendingPort)
        logger.info("Leash name(s): %s", ", ".join(self.Leashes))
        if self.VerboseLogging:
            logger.info("Verbose console logging enabled")
        logger.debug("Settings: %s", self.config)


class Leash:

    def __init__(self, paraName, contacts, settings: ConfigSettings):
        
        self.Name: str = paraName
        self.settings = settings

        self.Stretch: float = 0

        self.Z_Positive: float = 0
        self.Z_Negative: float = 0
        self.X_Positive: float = 0
        self.X_Negative: float = 0
        self.Y_Positive: float = 0
        self.Y_Negative: float = 0

        self.Grabbed: bool = False
        self.Active: bool = False

        if settings.TurningEnabled:
            self.LeashDirection = paraName.split("_")[-1]
            if self.LeashDirection not in ("North", "South", "East", "West"):
                logger.warning("Turning disabled for %s: use a _North, _South, _East or _West suffix", paraName)

        self.Z_Positive_ParamName: str = contacts["Z_Positive_Param"] #Forward
        self.Z_Negative_ParamName: str = contacts["Z_Negative_Param"] #Backward
        self.X_Positive_ParamName: str = contacts["X_Positive_Param"] #Right
        self.X_Negative_ParamName: str = contacts["X_Negative_Param"] #Left
        self.Y_Positive_ParamName: str = contacts["Y_Positive_Param"] #Up
        self.Y_Negative_ParamName: str = contacts["Y_Negative_Param"] #Down

    def resetMovement(self):
        self.Z_Positive: float = 0
        self.Z_Negative: float = 0
        self.X_Positive: float = 0
        self.X_Negative: float = 0
        self.Y_Positive: float = 0
        self.Y_Negative: float = 0

    def printDirections(self):
        print(f"\tZ: {round((self.Z_Positive), 2)},{round((self.Z_Negative), 2)} |  X: {round((self.X_Positive), 2)},{round((self.X_Negative), 2)} | Y: {round((self.Y_Positive), 2)},{round((self.Y_Negative), 2)}")
