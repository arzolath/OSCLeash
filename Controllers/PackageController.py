import logging
import math
import socket
from threading import Thread
import time

from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer

from Controllers.ThreadController import Program

logger = logging.getLogger(__name__)


class OSCServer(BlockingOSCUDPServer):
    def verify_request(self, request, client_address):
        valid = super().verify_request(request, client_address)
        if not valid:
            logger.debug("Ignoring non-OSC UDP packet from %s: %d bytes", client_address, len(request[0]))
        return valid


class Package:
    def __init__(self, leashCollection, useOSCQuery, program=None):
        if not leashCollection:
            raise ValueError("No leashes configured")
        self.leashes = leashCollection
        self.program = program if program is not None else Program()
        self._useOSCQuery = useOSCQuery
        self._dispatcher = Dispatcher()
        self._dispatcher.set_default_handler(self._receive, needs_reply_address=True)
        self._parameters = {}
        self._seen = set()
        self._received = 0
        self._matched = 0
        self._lastDiagnostic = time.monotonic()
        self._diagnosed = False
        self.server = None
        self._serverThread = None
        self._oscQueryService = None

    def listen(self):
        for leash in self.leashes:
            self._parameters[f'/avatar/parameters/{leash.Name}_Stretch'] = ("Stretch", [leash], float)
            self._parameters[f'/avatar/parameters/{leash.Name}_IsGrabbed'] = ("Grabbed", [leash], bool)
        for axis in ("Z_Positive", "Z_Negative", "X_Positive", "X_Negative", "Y_Positive", "Y_Negative"):
            name = getattr(self.leashes[0], f"{axis}_ParamName")
            self._parameters[f'/avatar/parameters/{name}'] = (axis, self.leashes, float)
        logger.debug("Expected OSC parameters: %s", ", ".join(self._parameters))

    def _receive(self, sender, address, *values):
        logger.debug("OSC RX %s:%s %s %r", sender[0], sender[1], address, values)
        with self.program.stateLock:
            self._received += 1
            if self._received == 1:
                logger.info("Receiving OSC from %s:%s", sender[0], sender[1])
            if address == '/avatar/change':
                if len(values) == 1 and isinstance(values[0], str):
                    logger.info("Avatar changed to %s; resetting leash state", values[0])
                    self.program.resetLeashes(self.leashes)
                    self._seen.clear()
                    self._matched = 0
                    self._diagnosed = False
                    self._lastDiagnostic = time.monotonic()
                return
            parameter = self._parameters.get(address)
            if parameter is None:
                logger.debug("Unmapped OSC address: %s", address)
                return
            attribute, leashes, valueType = parameter
            if len(values) != 1:
                logger.debug("Ignoring %s: expected one value, got %r", address, values)
                return
            value = values[0]
            if valueType is bool:
                if type(value) not in (bool, int, float) or value not in (0, 1):
                    logger.debug("Ignoring %s: expected a boolean or 0/1, got %r", address, value)
                    return
                value = bool(value)
            else:
                if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
                    logger.debug("Ignoring %s: expected a number between 0 and 1, got %r", address, value)
                    return
                value = float(value)
            self._matched += 1
            if address not in self._seen:
                self._seen.add(address)
                logger.info("Received parameter %s", address)
            for leash in leashes:
                setattr(leash, attribute, value)
            if attribute == "Grabbed":
                self.program.wake.set()

    def start(self, IP, Port):
        if self.server is not None:
            raise RuntimeError("OSC receiver is already running")
        # Resolve explicitly to IPv4 so 'localhost' agrees with VRChat and OSCQuery.
        bindIP = socket.gethostbyname(IP)
        if self._useOSCQuery and bindIP != "127.0.0.1":
            raise ValueError("UseOSCQuery currently requires BindIP=127.0.0.1. Use fixed ports for LAN setups.")
        listenPort = 0 if self._useOSCQuery else Port
        try:
            self.server = OSCServer((bindIP, listenPort), self._dispatcher)
        except OSError as exc:
            raise OSError(
                f"Cannot listen on {bindIP}:{listenPort}: {exc}. "
                "Check BindIP and close other receivers using this port, or enable UseOSCQuery."
            ) from exc
        try:
            self._serverThread = Thread(target=self._serve, name="OSC receiver", daemon=True)
            self._serverThread.start()
            logger.info("Listening for OSC on %s:%s (UDP)", *self.server.server_address)
            if self._useOSCQuery:
                from Controllers.QueryController import QueryService
                endpoints = {address: kind for address, (_, _, kind) in self._parameters.items()}
                endpoints['/avatar/change'] = str
                self._oscQueryService = QueryService(self.server.server_address[1], endpoints)
                self._oscQueryService.start()
                logger.info("OSCQuery advertised as %s on TCP port %s; ListeningPort is ignored",
                            self._oscQueryService.name, self._oscQueryService.httpPort)
            self._lastDiagnostic = time.monotonic()
        except BaseException:
            self.close()
            raise

    def _serve(self):
        try:
            self.server.serve_forever(poll_interval=0.1)
        except Exception:
            logger.exception("OSC receiver stopped unexpectedly")
        finally:
            self.program.stop()

    def checkConnection(self):
        with self.program.stateLock:
            if time.monotonic() - self._lastDiagnostic < 10:
                return
            self._lastDiagnostic = time.monotonic()
            missing = self._parameters.keys() - self._seen
            logger.debug("OSC received=%d matched=%d; parameters not seen: %s",
                         self._received, self._matched, ", ".join(sorted(missing)) or "none")
            if self._diagnosed:
                return
            self._diagnosed = True
            if not self._received:
                logger.warning("No OSC messages received. Enable OSC in VRChat and check its output port, "
                               "BindIP, firewall rules, and other OSC apps. With OSCQuery, check for "
                               "VRChat's OSCLeash discovery notification. See README troubleshooting.")
            elif not self._matched:
                logger.warning("OSC is arriving, but no valid leash parameters matched. Check the avatar's "
                               "OSC config and parameter names; enable VerboseLogging to see received addresses.")
            elif missing:
                logger.warning("Some parameters have not arrived yet: %s. Grab and stretch the leash to "
                               "exercise them; VRChat sends parameter changes.", ", ".join(sorted(missing)))

    def close(self):
        try:
            if self._oscQueryService is not None:
                self._oscQueryService.close()
                self._oscQueryService = None
        finally:
            if self.server is not None:
                if self._serverThread is not None and self._serverThread.is_alive():
                    self.server.shutdown()
                    self._serverThread.join()
                self.server.server_close()
                self.server = None
