from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable
from urllib.parse import urlparse


class ApiServer:
    def __init__(
        self,
        host: str,
        port: int,
        on_event: Callable[[dict], None],
        on_vscode_permission: Callable[[dict], dict] | None = None,
        on_bridge_feishu_notice: Callable[[dict], dict] | None = None,
        on_bridge_feishu_status: Callable[[dict], dict] | None = None,
        on_bridge_mqtt_notice: Callable[[dict], dict] | None = None,
        on_bridge_mqtt_status: Callable[[dict], dict] | None = None,
        on_bridge_mqtt_config: Callable[[], dict] | None = None,
        on_bridge_mqtt_helper_page: Callable[[], str] | None = None,
        on_hardware_refresh: Callable[[], dict] | None = None,
        on_hardware_command: Callable[[dict], dict] | None = None,
    ):
        self.host = host
        self.port = port
        self.on_event = on_event
        self.on_vscode_permission = on_vscode_permission
        self.on_bridge_feishu_notice = on_bridge_feishu_notice
        self.on_bridge_feishu_status = on_bridge_feishu_status
        self.on_bridge_mqtt_notice = on_bridge_mqtt_notice
        self.on_bridge_mqtt_status = on_bridge_mqtt_status
        self.on_bridge_mqtt_config = on_bridge_mqtt_config
        self.on_bridge_mqtt_helper_page = on_bridge_mqtt_helper_page
        self.on_hardware_refresh = on_hardware_refresh
        self.on_hardware_command = on_hardware_command
        self._server: ThreadingHTTPServer | None = None

    def start(self) -> None:
        outer = self

        class Handler(BaseHTTPRequestHandler):
            @staticmethod
            def _cors_headers() -> dict[str, str]:
                return {
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type",
                }

            @staticmethod
            def _json_headers() -> dict[str, str]:
                return {
                    **Handler._cors_headers(),
                    "Content-Type": "application/json",
                    "Cache-Control": "no-store",
                }

            @staticmethod
            def _html_headers() -> dict[str, str]:
                return {
                    **Handler._cors_headers(),
                    "Content-Type": "text/html; charset=utf-8",
                    "Cache-Control": "no-store",
                }

            def _route(self) -> str:
                return urlparse(self.path).path

            def _send_response(self, status_code: int, body: bytes = b"", headers: dict[str, str] | None = None) -> None:
                self.send_response(status_code)
                for key, value in (headers or {}).items():
                    self.send_header(key, value)
                self.end_headers()
                if body:
                    self.wfile.write(body)

            def _send_json(self, status_code: int, payload: dict) -> None:
                body = json.dumps(payload).encode("utf-8")
                self._send_response(status_code, body=body, headers=self._json_headers())

            def do_OPTIONS(self) -> None:  # noqa: N802
                route = self._route()
                if route not in {
                    "/events",
                    "/vscode/permission",
                    "/bridge/feishu-notice",
                    "/bridge/feishu-status",
                    "/bridge/mqtt-helper",
                    "/bridge/mqtt-config",
                    "/bridge/mqtt-notice",
                    "/bridge/mqtt-status",
                    "/hardware/refresh",
                    "/hardware/command",
                }:
                    self._send_response(404)
                    return
                headers = {
                    "Allow": "GET, POST, OPTIONS",
                    "Cache-Control": "no-store",
                    **self._cors_headers(),
                }
                if self.headers.get("Access-Control-Request-Private-Network") == "true":
                    headers["Access-Control-Allow-Private-Network"] = "true"
                self._send_response(204, headers=headers)

            def do_GET(self) -> None:  # noqa: N802
                route = self._route()
                if route == "/bridge/mqtt-helper":
                    if outer.on_bridge_mqtt_helper_page is None:
                        self._send_response(404)
                        return
                    page = outer.on_bridge_mqtt_helper_page()
                    self._send_response(200, body=page.encode("utf-8"), headers=self._html_headers())
                    return
                if route == "/bridge/mqtt-config":
                    if outer.on_bridge_mqtt_config is None:
                        self._send_response(404)
                        return
                    self._send_json(200, outer.on_bridge_mqtt_config())
                    return
                self._send_response(404)

            def do_POST(self) -> None:  # noqa: N802
                route = self._route()
                if route not in {
                    "/events",
                    "/vscode/permission",
                    "/bridge/feishu-notice",
                    "/bridge/feishu-status",
                    "/bridge/mqtt-notice",
                    "/bridge/mqtt-status",
                    "/hardware/refresh",
                    "/hardware/command",
                }:
                    self._send_response(404)
                    return

                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length) if length else b"{}"
                try:
                    payload = json.loads(raw.decode("utf-8") or "{}")
                except Exception:
                    self._send_response(400)
                    return

                response_payload = {"ok": True}
                if route == "/events":
                    outer.on_event(payload)
                elif route == "/vscode/permission":
                    if outer.on_vscode_permission is None:
                        self._send_response(404)
                        return
                    response_payload = outer.on_vscode_permission(payload)
                elif route == "/bridge/feishu-notice":
                    if outer.on_bridge_feishu_notice is None:
                        self._send_response(404)
                        return
                    response_payload = outer.on_bridge_feishu_notice(payload)
                elif route == "/bridge/feishu-status":
                    if outer.on_bridge_feishu_status is None:
                        self._send_response(404)
                        return
                    response_payload = outer.on_bridge_feishu_status(payload)
                elif route == "/bridge/mqtt-notice":
                    if outer.on_bridge_mqtt_notice is None:
                        self._send_response(404)
                        return
                    response_payload = outer.on_bridge_mqtt_notice(payload)
                elif route == "/bridge/mqtt-status":
                    if outer.on_bridge_mqtt_status is None:
                        self._send_response(404)
                        return
                    response_payload = outer.on_bridge_mqtt_status(payload)
                elif route == "/hardware/refresh":
                    if outer.on_hardware_refresh is None:
                        self._send_response(404)
                        return
                    response_payload = outer.on_hardware_refresh()
                elif route == "/hardware/command":
                    if outer.on_hardware_command is None:
                        self._send_response(404)
                        return
                    response_payload = outer.on_hardware_command(payload)

                self._send_json(200, response_payload)

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
