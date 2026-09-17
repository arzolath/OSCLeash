"""Serve a complete OSCQuery tree before announcing it to VRChat."""

import logging
import socket
from threading import Thread
from uuid import uuid4

from tinyoscquery.queryservice import OSCQueryHTTPHandler, OSCQueryHTTPServer
from tinyoscquery.shared.node import OSCAccess, OSCHostInfo, OSCQueryNode
from zeroconf import ServiceInfo, Zeroconf

logger = logging.getLogger(__name__)


class QueryService:
    def __init__(self, oscPort, endpoints):
        self.name = f"OSCLeash-{uuid4().hex[:8]}"
        self.oscPort = oscPort
        root = OSCQueryNode("/", description="OSCLeash")
        for address, valueType in endpoints.items():
            root.add_child_node(OSCQueryNode(address, type_=[valueType], access=OSCAccess.WRITEONLY_VALUE))
        host = OSCHostInfo(self.name, {"ACCESS": True, "TYPE": True}, "127.0.0.1", oscPort, "UDP")
        # Port 0 keeps the selected port reserved, unlike a probe followed by a second bind.
        self._http = OSCQueryHTTPServer(root, host, ("127.0.0.1", 0), OSCQueryHTTPHandler)
        self.httpPort = self._http.server_address[1]
        self._thread = None
        self._zeroconf = None

    def start(self):
        try:
            self._thread = Thread(target=self._http.serve_forever, kwargs={"poll_interval": 0.1},
                                  name="OSCQuery HTTP", daemon=True)
            self._thread.start()
            self._zeroconf = Zeroconf()
            for serviceType, port in (("_oscjson._tcp.local.", self.httpPort),
                                      ("_osc._udp.local.", self.oscPort)):
                info = ServiceInfo(
                    serviceType, f"{self.name}.{serviceType}",
                    addresses=[socket.inet_aton("127.0.0.1")], port=port,
                    properties={"txtvers": "1"}, server=f"{self.name}.local.")
                self._zeroconf.register_service(info)
                logger.debug("Registered %s on port %d", info.name, port)
        except BaseException:
            self.close()
            raise

    def close(self):
        try:
            if self._zeroconf is not None:
                try:
                    self._zeroconf.unregister_all_services()
                finally:
                    self._zeroconf.close()
                    self._zeroconf = None
        finally:
            if self._thread is not None and self._thread.is_alive():
                self._http.shutdown()
                self._thread.join()
            self._http.server_close()
