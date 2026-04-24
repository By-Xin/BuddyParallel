from __future__ import annotations

import os
from pathlib import Path
import socket
import threading
import time

import requests

from buddy_parallel.runtime.config import ConfigStore


def _post_json(api_base: str, path: str, payload: dict) -> None:
    response = requests.post(
        f"{api_base}{path}",
        json=payload,
        timeout=5,
    )
    response.raise_for_status()
def _parse_bool_line(line: str) -> bool | None:
    value = line.split(":", 1)[1].strip().lower()
    if value in {"true", "1", "yes", "on"}:
        return True
    if value in {"false", "0", "no", "off"}:
        return False
    return None


def _parse_int_line(line: str) -> int | None:
    try:
        return int(line.split(":", 1)[1].strip())
    except Exception:
        return None


def _port_listening(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=0.3):
            return True
    except OSError:
        return False


def _detect_proxy_candidates() -> list[tuple[str, str | None]]:
    candidates: list[tuple[str, str | None]] = [("direct", None)]
    ports: list[int] = []
    appdata = os.getenv("APPDATA", "")
    if appdata:
        base = Path(appdata) / "io.github.clash-verge-rev.clash-verge-rev"
        for path in (base / "verge.yaml", base / "config.yaml"):
            if not path.exists():
                continue
            try:
                for raw in path.read_text(encoding="utf-8").splitlines():
                    line = raw.strip()
                    if line.startswith("verge_mixed_port:") or line.startswith("mixed-port:") or line.startswith("port:"):
                        port = _parse_int_line(line)
                        if port:
                            ports.append(port)
            except OSError:
                pass

    ports.extend([7897, 7899])
    seen: set[int] = set()
    for port in ports:
        if port in seen:
            continue
        seen.add(port)
        if _port_listening(port):
            candidates.append((f"clash-http-127.0.0.1:{port}", f"http://127.0.0.1:{port}"))
    return candidates


def _report_status(api_base: str, *, connected: bool, error: str = "", summary: str = "") -> None:
    try:
        _post_json(
            api_base,
            "/bridge/feishu-status",
            {
                "connected": connected,
                "last_error": str(error or "")[:160],
                "last_message_summary": str(summary or "")[:40],
            },
        )
    except Exception:
        pass


def _build_proxy_aware_client(
    lark,
    *,
    app_id: str,
    app_secret: str,
    event_handler,
    proxy_url: str | None,
    log_level,
    on_connected=None,
):
    import http
    import requests as requests_lib
    import websockets
    from lark_oapi.core.const import UTF_8
    from lark_oapi.core.json import JSON
    from lark_oapi.ws.const import GEN_ENDPOINT_URI, OK, SYSTEM_BUSY, INTERNAL_ERROR
    from lark_oapi.ws.exception import ClientException, ServerException
    from lark_oapi.ws.model import EndpointResp

    class ProxyAwareClient(lark.ws.Client):
        def __init__(self) -> None:
            super().__init__(
                app_id,
                app_secret,
                event_handler=event_handler,
                log_level=log_level,
                auto_reconnect=False,
            )
            self._bp_proxy_url = proxy_url

        def _get_conn_url(self) -> str:
            if not self._app_id or not self._app_secret:
                raise ClientException(-1, "app_id or app_secret is null")

            request_kwargs = {
                "headers": {"locale": "zh"},
                "json": {"AppID": self._app_id, "AppSecret": self._app_secret},
                "timeout": 10,
            }
            session = requests_lib.Session()
            if self._bp_proxy_url:
                request_kwargs["proxies"] = {
                    "http": self._bp_proxy_url,
                    "https": self._bp_proxy_url,
                }
            else:
                session.trust_env = False
            response = session.post(self._domain + GEN_ENDPOINT_URI, **request_kwargs)
            if response.status_code != http.HTTPStatus.OK:
                raise ServerException(response.status_code, "system busy")

            resp = JSON.unmarshal(str(response.content, UTF_8), EndpointResp)
            if resp.code == OK:
                pass
            elif resp.code == SYSTEM_BUSY:
                raise ServerException(resp.code, "system busy")
            elif resp.code == INTERNAL_ERROR:
                raise ServerException(resp.code, resp.msg)
            else:
                raise ClientException(resp.code, resp.msg)

            data = resp.data
            if data.ClientConfig is not None:
                self._configure(data.ClientConfig)
            return data.URL

        async def _connect(self) -> None:
            await self._lock.acquire()
            if self._conn is not None:
                self._lock.release()
                return
            try:
                conn_url = self._get_conn_url()
                u = lark.ws.client.urlparse(conn_url)
                q = lark.ws.client.parse_qs(u.query)
                conn_id = q[lark.ws.const.DEVICE_ID][0]
                service_id = q[lark.ws.const.SERVICE_ID][0]

                kwargs = {}
                if self._bp_proxy_url:
                    kwargs["proxy"] = self._bp_proxy_url
                conn = await websockets.connect(conn_url, **kwargs)
                self._conn = conn
                self._conn_url = conn_url
                self._conn_id = conn_id
                self._service_id = service_id

                lark.ws.client.logger.info(self._fmt_log("connected to {}", conn_url))
                if on_connected is not None:
                    on_connected()
                lark.ws.client.loop.create_task(self._receive_message_loop())
            except websockets.InvalidStatusCode as exc:
                lark.ws.client._parse_ws_conn_exception(exc)
            finally:
                self._lock.release()

    return ProxyAwareClient()


def main(api_port: int | None = None) -> int:
    config = ConfigStore().load()
    port = int(api_port or config.api_server_port or 43112)
    api_base = f"http://127.0.0.1:{port}"

    if not config.feishu_app_id or not config.feishu_app_secret or not config.feishu_allowed_chat_id:
        _report_status(
            api_base,
            connected=False,
            error="configure Feishu app id, app secret, and allowed chat id",
        )
        return 1

    try:
        import lark_oapi as lark
    except Exception as exc:
        _report_status(api_base, connected=False, error=f"missing dependency: {exc}")
        return 1

    handle_lock = threading.Lock()

    def handle_message(data) -> None:
        with handle_lock:
            try:
                event = getattr(data, "event", None)
                message = getattr(event, "message", None)
                if message is None:
                    return

                chat_id = str(getattr(message, "chat_id", "") or "")
                if chat_id != config.feishu_allowed_chat_id:
                    return

                message_type = str(getattr(message, "message_type", "") or "").strip().lower()
                if message_type != "text":
                    return

                _post_json(
                    api_base,
                    "/bridge/feishu-notice",
                    {
                        "message_id": str(getattr(message, "message_id", "") or int(time.time())),
                        "create_time": getattr(message, "create_time", None),
                        "chat_id": chat_id,
                        "content": getattr(message, "content", "") or "",
                    },
                )
                try:
                    preview = ""
                    content_payload = getattr(message, "content", "") or ""
                    if isinstance(content_payload, str):
                        try:
                            import json

                            raw = json.loads(content_payload or "{}")
                            if isinstance(raw, dict):
                                preview = str(raw.get("text") or "").strip()[:40]
                        except Exception:
                            preview = content_payload[:40]
                    _report_status(api_base, connected=True, error="", summary=preview)
                except Exception:
                    pass
            except Exception as exc:
                _report_status(api_base, connected=False, error=str(exc))

    event_handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(handle_message)
        .build()
    )

    errors: list[str] = []
    for label, proxy_url in _detect_proxy_candidates():
        _report_status(api_base, connected=False, error="", summary=f"connecting via {label}")
        try:
            client = _build_proxy_aware_client(
                lark,
                app_id=config.feishu_app_id,
                app_secret=config.feishu_app_secret,
                event_handler=event_handler,
                proxy_url=proxy_url,
                log_level=lark.LogLevel.WARNING,
                on_connected=lambda current_label=label: _report_status(
                    api_base,
                    connected=True,
                    error="",
                    summary=f"Feishu long connection via {current_label}",
                ),
            )
            client.start()
            return 0
        except Exception as exc:
            errors.append(f"{label}: {exc}")

    _report_status(api_base, connected=False, error=" | ".join(errors)[:160])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
