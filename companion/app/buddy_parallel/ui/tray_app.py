from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

from PIL import Image, ImageDraw

from buddy_parallel import __version__
from buddy_parallel.core.companion_runtime import CompanionRuntime
from buddy_parallel.ingest.install_hooks import main as install_hooks_main
from buddy_parallel.runtime.config import APP_DIR, CONFIG_PATH, LOG_PATH, AppConfig, ConfigStore
from buddy_parallel.runtime.logging_utils import configure_logging
from buddy_parallel.runtime.runtime_config import read_runtime_config
from buddy_parallel.runtime.state import StateStore
from buddy_parallel.services.telegram_bridge import TelegramBridge
from buddy_parallel.services.updates import UpdateChecker


class BuddyParallelApp:
    def __init__(self, headless: bool = False) -> None:
        self.headless = headless
        self.logger = configure_logging()
        self.config_store = ConfigStore()
        self.state_store = StateStore()
        self.update_checker = UpdateChecker()
        self.telegram_bridge = TelegramBridge(self._load_config, self._post_telegram_message, self.logger, self.state_store)
        self._runtime: CompanionRuntime | None = None
        self._current_config: AppConfig | None = None
        self._runtime_lock = threading.RLock()
        self._stopping = False
        self._settings_process: subprocess.Popen | None = None
        self._watcher: threading.Thread | None = None
        self._config_mtime = 0.0

        if not self.headless:
            try:
                import pystray
                from pystray import MenuItem as Item
            except ImportError as exc:
                raise SystemExit("missing dependency: pip install pystray pillow") from exc

            self._pystray = pystray
            self._Item = Item
            self._icon = pystray.Icon("buddy-parallel", self._make_icon(), "BuddyParallel", self._build_menu())
        else:
            self._pystray = None
            self._Item = None
            self._icon = None

    def run(self) -> None:
        config = self.config_store.load()
        state = self.state_store.load()
        self.logger.info("BuddyParallel starting")
        self.logger.info(
            "transport_mode=%s device_name=%s last_status=%s",
            config.transport_mode,
            config.device_name,
            state.last_status,
        )

        APP_DIR.mkdir(parents=True, exist_ok=True)
        self._config_mtime = self._get_config_mtime()
        self._current_config = config

        if self.headless:
            print("BuddyParallel companion running in headless mode.")
            self._start_runtime(config)
            self.telegram_bridge.start()
            self._run_headless_loop()
            return

        self._start_runtime(config)
        self.telegram_bridge.start()
        self._watcher = threading.Thread(target=self._watch_config_loop, name="bp-config-watcher", daemon=True)
        self._watcher.start()
        assert self._icon is not None
        self._icon.run()

    def snapshot(self) -> dict:
        runtime = read_runtime_config()
        state = self.state_store.load()
        return {
            "runtime": runtime,
            "state": {
                "last_transport": state.last_transport,
                "last_device_id": state.last_device_id,
                "last_status": state.last_status,
                "last_error": state.last_error,
                "telegram_offset": state.telegram_offset,
                "last_telegram_error": state.last_telegram_error,
                "last_telegram_message_summary": state.last_telegram_message_summary,
                "last_telegram_delivery_at": state.last_telegram_delivery_at,
            },
        }

    def install_hooks(self) -> None:
        install_hooks_main()

    def stop(self) -> None:
        self._stopping = True
        self.telegram_bridge.stop()
        self._stop_runtime()
        if self._icon is not None:
            self._icon.stop()

    def _run_headless_loop(self) -> None:
        try:
            while not self._stopping:
                time.sleep(0.25)
        except KeyboardInterrupt:
            self.logger.info("Keyboard interrupt received; stopping runtime")
            self.stop()

    def _build_menu(self):
        assert self._pystray is not None
        assert self._Item is not None
        return self._pystray.Menu(
            self._Item(lambda item: self._status_label(), None, enabled=False),
            self._Item(lambda item: self._detail_label(), None, enabled=False),
            self._Item(lambda item: self._telegram_label(), None, enabled=False),
            self._Item("Open Settings", self._open_settings),
            self._Item("Install Hooks", self._install_hooks),
            self._Item("Open Config File", self._open_config_file),
            self._Item("Open Log File", self._open_log_file),
            self._Item("Open Runtime File", self._open_runtime_file),
            self._Item("Check Updates", self._check_updates),
            self._Item(f"Version {__version__}", None, enabled=False),
            self._Item("Quit", self._quit),
        )

    def _status_label(self) -> str:
        runtime = read_runtime_config()
        heartbeat = runtime.get("heartbeat") if isinstance(runtime, dict) else {}
        transport = str(runtime.get("transport") or "idle") if isinstance(runtime, dict) else "idle"
        running = int(heartbeat.get("running") or 0) if isinstance(heartbeat, dict) else 0
        waiting = int(heartbeat.get("waiting") or 0) if isinstance(heartbeat, dict) else 0
        total = int(heartbeat.get("total") or 0) if isinstance(heartbeat, dict) else 0
        return f"{transport} | sessions {total} | running {running} | waiting {waiting}"

    def _detail_label(self) -> str:
        runtime = read_runtime_config()
        heartbeat = runtime.get("heartbeat") if isinstance(runtime, dict) else {}
        msg = str(heartbeat.get("msg") or "No Claude connected") if isinstance(heartbeat, dict) else "No Claude connected"
        return msg[:64]

    def _telegram_label(self) -> str:
        status = self.telegram_bridge.status()
        prefix = "Telegram OK" if status.telegram_ok else "Telegram idle"
        detail = status.last_error or status.last_message_summary
        return f"{prefix} | {detail[:48]}"

    def _open_settings(self, icon=None, item=None) -> None:
        if self._settings_process and self._settings_process.poll() is None:
            return
        script = Path(__file__).resolve().parents[3] / "scripts" / "run_settings.py"
        self._settings_process = subprocess.Popen([sys.executable, str(script)])

    def _install_hooks(self, icon=None, item=None) -> None:
        try:
            self.install_hooks()
            self._notify("BuddyParallel hooks installed.")
        except Exception as exc:
            self._notify(f"Hook install failed: {exc}")

    def _open_config_file(self, icon=None, item=None) -> None:
        self._open_path(CONFIG_PATH)

    def _open_log_file(self, icon=None, item=None) -> None:
        self._open_path(LOG_PATH)

    def _open_runtime_file(self, icon=None, item=None) -> None:
        from buddy_parallel.runtime.config import RUNTIME_PATH

        self._open_path(RUNTIME_PATH)

    def _check_updates(self, icon=None, item=None) -> None:
        info = self.update_checker.check(self.config_store.load())
        if info.error:
            self._notify(self.update_checker.build_error_message(info.error))
            return
        if not info.available:
            self._notify(self.update_checker.build_up_to_date_message())
            return
        self._notify(self.update_checker.build_available_message(info))
        if info.open_url:
            webbrowser.open(info.open_url)

    def _quit(self, icon=None, item=None) -> None:
        self.stop()

    def _notify(self, message: str) -> None:
        self.logger.info(message)
        if self._icon is None:
            return
        try:
            self._icon.notify(message, "BuddyParallel")
        except Exception:
            pass

    def _watch_config_loop(self) -> None:
        while not self._stopping:
            try:
                current = self._get_config_mtime()
                if current != self._config_mtime:
                    self._config_mtime = current
                    self._reload_config()
                    if self._icon is not None:
                        self._icon.update_menu()
            except Exception as exc:
                self.logger.error("Config watcher failed: %s", exc)
            time.sleep(1.0)

    def _reload_config(self) -> None:
        new_config = self.config_store.load()
        old_config = self._current_config
        self._current_config = new_config
        if old_config is None or self._requires_runtime_restart(old_config, new_config):
            self.logger.info("Config changed; restarting runtime")
            self._stop_runtime()
            self._start_runtime(new_config)
            self.telegram_bridge.request_reload()
            self._notify("BuddyParallel runtime configuration reloaded.")
            return
        self.logger.info("Config changed; updating non-runtime services only")
        self.telegram_bridge.request_reload()
        self._notify("BuddyParallel settings updated.")

    def _start_runtime(self, config: AppConfig) -> None:
        with self._runtime_lock:
            runtime = CompanionRuntime(config=config, state_store=self.state_store)
            runtime.start()
            self._runtime = runtime

    def _stop_runtime(self) -> None:
        with self._runtime_lock:
            runtime = self._runtime
            self._runtime = None
        if runtime is not None:
            runtime.stop()

    def _get_config_mtime(self) -> float:
        return self.config_store.path.stat().st_mtime if self.config_store.path.exists() else 0.0

    def _load_config(self) -> AppConfig:
        return self.config_store.load()

    @staticmethod
    def _requires_runtime_restart(old: AppConfig, new: AppConfig) -> bool:
        return any(
            getattr(old, key) != getattr(new, key)
            for key in (
                "transport_mode",
                "serial_port",
                "serial_baud",
                "ble_device_name",
                "hook_server_port",
                "api_server_port",
                "owner_name",
                "device_name",
            )
        )

    def _post_telegram_message(self, message: str, entries: list[str] | None, ttl_seconds: float) -> None:
        with self._runtime_lock:
            runtime = self._runtime
        if runtime is None:
            return
        runtime.post_transient_message(message=message, entries=entries, ttl_seconds=ttl_seconds)
        if self._icon is not None:
            self._icon.update_menu()

    @staticmethod
    def _open_path(path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.touch()
        if hasattr(os, "startfile"):
            os.startfile(path)
        else:
            webbrowser.open(path.as_uri())

    @staticmethod
    def _make_icon() -> Image.Image:
        image = Image.new("RGBA", (64, 64), (244, 240, 226, 255))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((8, 8, 56, 56), radius=12, fill=(33, 53, 85, 255), outline=(245, 166, 35, 255), width=3)
        draw.ellipse((18, 16, 46, 44), fill=(91, 192, 190, 255))
        draw.rectangle((24, 28, 40, 48), fill=(245, 166, 35, 255))
        return image
