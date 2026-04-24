from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Callable

from buddy_parallel.runtime.config import AppConfig
from buddy_parallel.runtime.state import StateStore
from buddy_parallel.services.launching import build_companion_command


@dataclass
class BridgeStatus:
    feishu_ok: bool = False
    last_error: str = ""
    last_message_summary: str = "idle"


class FeishuBridge:
    def __init__(
        self,
        config_supplier: Callable[[], AppConfig],
        logger: logging.Logger,
        state_store: StateStore,
    ) -> None:
        self._config_supplier = config_supplier
        self._logger = logger
        self._state_store = state_store
        runtime_state = self._state_store.load()
        self._status = BridgeStatus(
            feishu_ok=bool(runtime_state.feishu_connected and not runtime_state.last_feishu_error),
            last_error=runtime_state.last_feishu_error,
            last_message_summary=runtime_state.last_feishu_message_summary,
        )
        self._thread: threading.Thread | None = None
        self._process: subprocess.Popen | None = None
        self._stop = threading.Event()
        self._reload = threading.Event()
        self._lock = threading.Lock()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._reload.clear()
        self._thread = threading.Thread(target=self._run, name="bp-feishu", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._reload.set()
        self._terminate_process()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def request_reload(self) -> None:
        self._reload.set()
        self._terminate_process()

    def status(self) -> BridgeStatus:
        self._refresh_status(process_alive=self._process_alive())
        with self._lock:
            return BridgeStatus(**self._status.__dict__)

    def _set_status(self, **kwargs) -> None:
        with self._lock:
            for key, value in kwargs.items():
                setattr(self._status, key, value)

    def _sleep_or_reload(self, seconds: float) -> None:
        self._reload.wait(timeout=seconds)
        self._reload.clear()

    def _process_alive(self) -> bool:
        process = self._process
        return process is not None and process.poll() is None

    def _refresh_status(self, *, process_alive: bool) -> None:
        runtime_state = self._state_store.load()
        last_error = runtime_state.last_feishu_error
        last_summary = runtime_state.last_feishu_message_summary
        self._set_status(
            feishu_ok=bool(process_alive and not last_error),
            last_error=last_error,
            last_message_summary=last_summary,
        )

    def _spawn_process(self, config: AppConfig) -> subprocess.Popen:
        launch = build_companion_command("feishu-helper", "--api-port", str(config.api_server_port), windowed=(os.name == "nt"))
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        self._logger.info("Starting Feishu bridge helper")
        return subprocess.Popen(launch.command, cwd=str(launch.working_dir), creationflags=creationflags)

    def _terminate_process(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        if process.poll() is not None:
            return
        try:
            process.terminate()
            process.wait(timeout=3.0)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

    def _run(self) -> None:
        while not self._stop.is_set():
            config = self._config_supplier()
            if not config.feishu_app_id or not config.feishu_app_secret or not config.feishu_allowed_chat_id:
                message = "configure Feishu app id, app secret, and allowed chat id"
                self._set_status(feishu_ok=False, last_error=message)
                self._state_store.update(feishu_connected=False, last_feishu_error=message)
                self._sleep_or_reload(2.0)
                continue

            self._state_store.update(
                feishu_connected=False,
                last_feishu_error="",
                last_feishu_message_summary="starting",
            )
            try:
                self._process = self._spawn_process(config)
            except Exception as exc:
                message = str(exc)
                self._logger.exception("Failed to start Feishu bridge helper")
                self._state_store.update(feishu_connected=False, last_feishu_error=message)
                self._set_status(feishu_ok=False, last_error=message)
                self._sleep_or_reload(3.0)
                continue

            while not self._stop.is_set():
                should_backoff = False
                if self._reload.wait(timeout=1.0):
                    self._reload.clear()
                    break

                if not self._process_alive():
                    runtime_state = self._state_store.load()
                    if not runtime_state.last_feishu_error:
                        self._state_store.update(
                            feishu_connected=False,
                            last_feishu_error="Feishu bridge helper exited",
                        )
                    should_backoff = True
                    break
                self._refresh_status(process_alive=True)

            self._terminate_process()
            self._refresh_status(process_alive=False)
            if should_backoff and not self._stop.is_set():
                self._sleep_or_reload(30.0)
