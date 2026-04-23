from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable


class ApiServer:
    def __init__(
        self,
        host: str,
        port: int,
        on_event: Callable[[dict], None],
        on_vscode_permission: Callable[[dict], dict] | None = None,
    ):
        self.host = host
        self.port = port
        self.on_event = on_event
        self.on_vscode_permission = on_vscode_permission
        self._server: ThreadingHTTPServer | None = None

    def start(self) -> None:
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                if self.path not in {"/events", "/vscode/permission"}:
                    self.send_response(404)
                    self.end_headers()
                    return

                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length) if length else b"{}"
                try:
                    import json

                    payload = json.loads(raw.decode("utf-8") or "{}")
                except Exception:
                    self.send_response(400)
                    self.end_headers()
                    return

                response_payload = {"ok": True}
                if self.path == "/events":
                    outer.on_event(payload)
                else:
                    if outer.on_vscode_permission is None:
                        self.send_response(404)
                        self.end_headers()
                        return
                    response_payload = outer.on_vscode_permission(payload)

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(response_payload).encode("utf-8"))

            def log_message(self, format: str, *args) -> None:
                return

        self._server = ThreadingHTTPServer((self.host, self.port), Handler)

    def serve_forever(self) -> None:
        if self._server is None:
            self.start()
        assert self._server is not None
        self._server.serve_forever()

    def shutdown(self) -> None:
        if self._server is not None:
            self._server.shutdown()
