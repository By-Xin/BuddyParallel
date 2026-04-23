from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import webbrowser
from dataclasses import replace
from pathlib import Path

from PIL import Image, ImageDraw

from buddy_parallel import __version__
from buddy_parallel.core.companion_runtime import CompanionRuntime
from buddy_parallel.core.hardware_state import (
    GIF_PET_INDEX,
    brightness_display,
    parse_hardware_snapshot,
    pet_choices,
    pet_display_name,
)
from buddy_parallel.ingest.install_hooks import main as install_hooks_main
from buddy_parallel.runtime.config import APP_DIR, CONFIG_PATH, LOG_PATH, AppConfig, ConfigStore
from buddy_parallel.runtime.logging_utils import configure_logging
from buddy_parallel.runtime.runtime_config import read_runtime_config
from buddy_parallel.runtime.state import StateStore
from buddy_parallel.services.startup import StartupManager
from buddy_parallel.services.telegram_bridge import TelegramBridge
from buddy_parallel.services.updates import UpdateChecker
from buddy_parallel.services.weather_bridge import WeatherBridge
from buddy_parallel.transports.serial_transport import discover_serial_devices


class BuddyParallelApp:
    def __init__(self, headless: bool = False) -> None:
        self.headless = headless
        self.logger = configure_logging()
        self.config_store = ConfigStore()
        self.state_store = StateStore()
        self.update_checker = UpdateChecker()
        self.startup_manager = StartupManager()
        self.telegram_bridge = TelegramBridge(self._load_config, self._post_telegram_message, self.logger, self.state_store)
        self.weather_bridge = WeatherBridge(self._load_config, self._apply_weather_snapshot, self.logger, self.state_store)
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
        self._sync_startup(config)

        if self.headless:
            print("BuddyParallel companion running in headless mode.")
            self._start_runtime(config)
            self.weather_bridge.start()
            self.telegram_bridge.start()
            self._run_headless_loop()
            return

        self._start_runtime(config)
        self.weather_bridge.start()
        self.telegram_bridge.start()
        self._watcher = threading.Thread(target=self._watch_config_loop, name="bp-config-watcher", daemon=True)
        self._watcher.start()
        self._refresh_menu()
        assert self._icon is not None
        self._icon.run()

    def snapshot(self) -> dict:
        runtime = read_runtime_config()
        state = self.state_store.load()
        return {
            "runtime": runtime,
            "hardware": parse_hardware_snapshot(runtime.get("device_status") if isinstance(runtime, dict) else None).__dict__,
            "state": {
                "last_transport": state.last_transport,
                "last_device_id": state.last_device_id,
                "last_status": state.last_status,
                "last_error": state.last_error,
                "weather_location_name": state.weather_location_name,
                "last_weather_error": state.last_weather_error,
                "last_weather_summary": state.last_weather_summary,
                "last_weather_update_at": state.last_weather_update_at,
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
        self.weather_bridge.stop()
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
        hardware_menu = self._build_hardware_menu()
        port_menu = self._build_port_menu()
        files_menu = self._pystray.Menu(
            self._Item("Open Config File", self._open_config_file),
            self._Item("Open Log File", self._open_log_file),
            self._Item("Open Runtime File", self._open_runtime_file),
        )
        return self._pystray.Menu(
            self._Item(lambda item: self._status_label(), None, enabled=False),
            self._Item(lambda item: self._detail_label(), None, enabled=False),
            self._Item(lambda item: self._weather_label(), None, enabled=False),
            self._Item(lambda item: self._telegram_label(), None, enabled=False),
            self._Item(lambda item: self._hardware_label(), None, enabled=False),
            self._Item(lambda item: self._hardware_controls_label(), None, enabled=False),
            self._Item("Hardware Controls", hardware_menu),
            self._Item("Serial Port", port_menu),
            self._Item("Open Settings", self._open_settings),
            self._Item("Install Hooks", self._install_hooks),
            self._Item("Logs & Files", files_menu),
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

    def _weather_label(self) -> str:
        config = self.config_store.load()
        if not config.weather_enabled:
            return "Weather off"
        status = self.weather_bridge.status()
        prefix = "Weather OK" if status.weather_ok else "Weather idle"
        location = f"{status.location_name} | " if status.location_name else ""
        detail = status.last_error or status.last_summary
        return f"{prefix} | {location}{detail[:44]}"

    def _hardware_label(self) -> str:
        runtime = read_runtime_config()
        hardware = parse_hardware_snapshot(runtime.get("device_status") if isinstance(runtime, dict) else None)
        port = str(runtime.get("device_port") or "") if isinstance(runtime, dict) else ""
        if not hardware.connected:
            target = port or self.config_store.load().serial_port or "auto"
            return f"Hardware idle | port {target}"
        battery = f"{hardware.battery_pct}%" if hardware.battery_pct is not None else "?"
        power = " USB" if hardware.usb_powered else ""
        pet = pet_display_name(hardware.pet_name)
        device_name = hardware.name or "Buddy"
        return f"{device_name} | {pet} | battery {battery}{power}"

    def _hardware_controls_label(self) -> str:
        runtime = read_runtime_config()
        hardware = parse_hardware_snapshot(runtime.get("device_status") if isinstance(runtime, dict) else None)
        brightness = brightness_display(hardware.brightness)
        sound = self._on_off_label(hardware.sound_enabled)
        led = self._on_off_label(hardware.led_enabled)
        return f"Controls | brightness {brightness} | sound {sound} | led {led}"

    def _build_hardware_menu(self):
        assert self._pystray is not None
        assert self._Item is not None
        return self._pystray.Menu(
            self._Item("Refresh Status", self._refresh_device_status),
            self._Item(lambda item: self._hardware_device_line(), None, enabled=False),
            self._Item(lambda item: self._hardware_battery_line(), None, enabled=False),
            self._Item("Brightness", self._build_brightness_menu(), enabled=lambda item: self._device_available()),
            self._Item(
                "LED Enabled",
                self._toggle_led,
                enabled=lambda item: self._device_available(),
                checked=lambda item: self._hardware_snapshot().led_enabled is True,
            ),
            self._Item(
                "Sound Enabled",
                self._toggle_sound,
                enabled=lambda item: self._device_available(),
                checked=lambda item: self._hardware_snapshot().sound_enabled is True,
            ),
            self._Item("Pet", self._build_pet_menu(), enabled=lambda item: self._device_available()),
        )

    def _build_brightness_menu(self):
        assert self._pystray is not None
        assert self._Item is not None
        items = []
        for level in range(5):
            items.append(
                self._Item(
                    f"{level}/4",
                    lambda icon, item, level=level: self._set_brightness(level),
                    enabled=lambda item: self._device_available(),
                    checked=lambda item, level=level: self._hardware_snapshot().brightness == level,
                    radio=True,
                )
            )
        return self._pystray.Menu(*items)

    def _build_pet_menu(self):
        assert self._pystray is not None
        assert self._Item is not None
        hardware = self._hardware_snapshot()
        items = []
        for pet_index, label in pet_choices(hardware):
            items.append(
                self._Item(
                    label,
                    lambda icon, item, pet_index=pet_index: self._set_pet(pet_index),
                    enabled=lambda item: self._device_available(),
                    checked=lambda item, pet_index=pet_index: self._current_pet_index() == pet_index,
                    radio=True,
                )
            )
        if not items:
            items.append(self._Item("No pet options", None, enabled=False))
        return self._pystray.Menu(*items)

    def _build_port_menu(self):
        assert self._pystray is not None
        assert self._Item is not None
        items = [
            self._Item(
                "Auto Detect",
                lambda icon, item: self._select_serial_port(""),
                checked=lambda item: not self.config_store.load().serial_port,
                radio=True,
            )
        ]
        for device in discover_serial_devices():
            label = device.device
            detail = f" {device.description}".strip()
            if detail:
                label = f"{label} | {detail[:28]}"
            items.append(
                self._Item(
                    label,
                    lambda icon, item, port=device.device: self._select_serial_port(port),
                    checked=lambda item, port=device.device: self.config_store.load().serial_port == port,
                    radio=True,
                )
            )
        if len(items) == 1:
            items.append(self._Item("No serial ports found", None, enabled=False))
        return self._pystray.Menu(*items)

    def _hardware_device_line(self) -> str:
        hardware = self._hardware_snapshot()
        if not hardware.connected:
            return "Device | not connected"
        pet = pet_display_name(hardware.pet_name)
        return f"Device | {hardware.name or 'Buddy'} | pet {pet}"

    def _hardware_battery_line(self) -> str:
        hardware = self._hardware_snapshot()
        if not hardware.connected:
            return "Battery | unavailable"
        battery = f"{hardware.battery_pct}%" if hardware.battery_pct is not None else "?"
        power = "USB powered" if hardware.usb_powered else "battery only"
        return f"Battery | {battery} | {power}"

    def _hardware_snapshot(self):
        runtime = read_runtime_config()
        status = runtime.get("device_status") if isinstance(runtime, dict) else None
        return parse_hardware_snapshot(status)

    def _device_available(self) -> bool:
        return self._hardware_snapshot().connected

    def _current_pet_index(self) -> int | None:
        hardware = self._hardware_snapshot()
        return hardware.pet_index if hardware.pet_index is not None else (GIF_PET_INDEX if hardware.pet_mode == "gif" else None)

    @staticmethod
    def _on_off_label(value: bool | None) -> str:
        if value is None:
            return "?"
        return "on" if value else "off"

    def _refresh_menu(self) -> None:
        if self._icon is None:
            return
        try:
            self._icon.menu = self._build_menu()
        except Exception:
            pass
        try:
            self._icon.update_menu()
        except Exception:
            pass

    def _select_serial_port(self, port: str) -> None:
        config = self.config_store.load()
        if config.serial_port == port:
            return
        self._save_config(replace(config, serial_port=port))

    def _save_config(self, config: AppConfig) -> None:
        self.config_store.save(config)
        self._config_mtime = self._get_config_mtime()
        self._reload_config()
        self._refresh_menu()

    def _refresh_device_status(self, icon=None, item=None) -> None:
        status = self._run_runtime_action(lambda runtime: runtime.refresh_device_status())
        if status is None:
            self._notify("No hardware device is currently reachable.")
            return
        self._notify("Hardware status refreshed.")

    def _set_brightness(self, level: int) -> None:
        self._apply_device_command({"cmd": "brightness", "level": level}, f"Brightness set to {level}/4.")

    def _toggle_led(self, icon=None, item=None) -> None:
        current = self._hardware_snapshot().led_enabled
        if current is None:
            self._notify("LED state is unavailable right now.")
            return
        next_value = not current
        self._apply_device_command({"cmd": "led", "on": next_value}, f"LED {'enabled' if next_value else 'disabled'}.")

    def _toggle_sound(self, icon=None, item=None) -> None:
        current = self._hardware_snapshot().sound_enabled
        if current is None:
            self._notify("Sound state is unavailable right now.")
            return
        next_value = not current
        self._apply_device_command({"cmd": "sound", "on": next_value}, f"Sound {'enabled' if next_value else 'muted'}.")

    def _set_pet(self, pet_index: int) -> None:
        status = self._run_runtime_action(lambda runtime: runtime.apply_device_command({"cmd": "species", "idx": pet_index}))
        if status is None:
            self._notify("Unable to update the pet right now.")
            return
        pet_name = parse_hardware_snapshot(status).pet_name or ("gif" if pet_index == GIF_PET_INDEX else "")
        self._notify(f"Pet switched to {pet_display_name(pet_name)}.")

    def _apply_device_command(self, payload: dict, success_message: str) -> None:
        status = self._run_runtime_action(lambda runtime: runtime.apply_device_command(payload))
        if status is None:
            self._notify("No hardware device is currently reachable.")
            return
        self._notify(success_message)

    def _run_runtime_action(self, action):
        with self._runtime_lock:
            runtime = self._runtime
        if runtime is None:
            return None
        try:
            result = action(runtime)
        except Exception as exc:
            self._notify(f"Hardware action failed: {exc}")
            return None
        self._refresh_menu()
        return result

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
                    self._refresh_menu()
            except Exception as exc:
                self.logger.error("Config watcher failed: %s", exc)
            time.sleep(1.0)

    def _reload_config(self) -> None:
        new_config = self.config_store.load()
        old_config = self._current_config
        self._current_config = new_config
        auto_start_changed = old_config is not None and old_config.auto_start != new_config.auto_start
        self._sync_startup(new_config, notify=auto_start_changed)
        if old_config is None or self._requires_runtime_restart(old_config, new_config):
            self.logger.info("Config changed; restarting runtime")
            self._stop_runtime()
            self._start_runtime(new_config)
            self.weather_bridge.request_reload()
            self.telegram_bridge.request_reload()
            self._notify("BuddyParallel runtime configuration reloaded.")
            self._refresh_menu()
            return
        self.logger.info("Config changed; updating non-runtime services only")
        self.weather_bridge.request_reload()
        self.telegram_bridge.request_reload()
        self._notify("BuddyParallel settings updated.")
        self._refresh_menu()

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

    def _post_telegram_message(
        self,
        message: str,
        entries: list[str] | None,
        ttl_seconds: float,
        notice_id: str,
        notice_from: str,
        notice_body: str,
        notice_stamp: str,
    ) -> None:
        with self._runtime_lock:
            runtime = self._runtime
        if runtime is None:
            return
        runtime.post_transient_message(
            message=message,
            entries=entries,
            ttl_seconds=ttl_seconds,
            notice_id=notice_id,
            notice_from=notice_from,
            notice_body=notice_body,
            notice_stamp=notice_stamp,
        )
        self._refresh_menu()

    def _apply_weather_snapshot(self, payload: dict | None) -> None:
        with self._runtime_lock:
            runtime = self._runtime
        if runtime is None:
            return
        runtime.set_weather_snapshot(payload)
        self._refresh_menu()

    def _sync_startup(self, config: AppConfig, notify: bool = False) -> None:
        try:
            target, arguments, working_dir = self._startup_command()
            self.startup_manager.apply(
                enabled=config.auto_start,
                target=target,
                arguments=arguments,
                working_dir=working_dir,
            )
            if notify:
                state = "enabled" if config.auto_start else "disabled"
                self._notify(f"Launch at startup {state}.")
        except Exception as exc:
            self.logger.error("Failed to sync startup entry: %s", exc)
            if notify:
                self._notify(f"Launch at startup update failed: {exc}")

    def _startup_command(self) -> tuple[Path, list[str], Path]:
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve(), [], Path(sys.executable).resolve().parent
        companion_dir = Path(__file__).resolve().parents[3]
        repo_root = companion_dir.parent
        script = companion_dir / "scripts" / "run_companion.py"
        return script, ["run"], repo_root

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
