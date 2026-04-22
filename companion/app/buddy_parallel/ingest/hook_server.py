from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

from buddy_parallel.runtime.logging_utils import configure_logging


class HookServer:
    def __init__(self, host: str, port: int, on_state: Callable[[dict], None], on_permission: Callable[[BaseHTTPRequestHandler, dict], None]):
        self.host = host
        self.port = port
        self.on_state = on_state
        self.on_permission = on_permission
        self.logger = configure_logging()
        self._server: ThreadingHTTPServer | None = None

    def start(self) -> None:
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length) if length else b"{}"
                try:
                    import json

                    payload = json.loads(raw.decode("utf-8") or "{}")
                except Exception:
                    self.send_response(400)
                    self.end_headers()
                    return

                if self.path == "/state":
                    outer.on_state(payload)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"ok":true}')
                    return

                if self.path == "/permission":
                    outer.on_permission(self, payload)
                    return

                self.send_response(404)
                self.end_headers()

            def log_message(self, format: str, *args) -> None:
                outer.logger.info("hook-server " + format, *args)

        self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        self.logger.info("Hook server listening on %s:%s", self.host, self.port)

    def serve_forever(self) -> None:
        if self._server is None:
            self.start()
        assert self._server is not None
        self._server.serve_forever()

    def shutdown(self) -> None:
        if self._server is not None:
            self._server.shutdown()
