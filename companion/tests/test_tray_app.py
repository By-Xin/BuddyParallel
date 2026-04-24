from __future__ import annotations

import importlib
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from buddy_parallel.runtime.config import AppConfig


class _FakeMenu:
    def __init__(self, *items) -> None:
        self.items = items


class _FakeMenuItem:
    def __init__(self, text, action, enabled=True, checked=None, radio=False) -> None:
        self.text = text
        self.action = action
        self.enabled = enabled
        self.checked = checked
        self.radio = radio


class _FakePystray:
    Menu = _FakeMenu


class _FakeConfigStore:
    def load(self) -> AppConfig:
        return AppConfig()


class _FakeStatusBridge:
    def __init__(self, **kwargs) -> None:
        self._status = SimpleNamespace(**kwargs)

    def status(self):
        return self._status


class TrayAppMenuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            cls.tray_app = importlib.import_module("buddy_parallel.ui.tray_app")
        except ImportError as exc:
            raise unittest.SkipTest(f"tray dependencies unavailable: {exc}") from exc

    def _make_app(self):
        app = self.tray_app.BuddyParallelApp.__new__(self.tray_app.BuddyParallelApp)
        app._pystray = _FakePystray
        app._Item = _FakeMenuItem
        app.config_store = _FakeConfigStore()
        app.weather_bridge = _FakeStatusBridge(
            weather_ok=False,
            location_name="",
            last_error="",
            last_summary="idle",
        )
        app.telegram_bridge = _FakeStatusBridge(
            telegram_ok=False,
            last_error="",
            last_message_summary="idle",
        )
        app.feishu_bridge = _FakeStatusBridge(
            feishu_ok=False,
            last_error="",
            last_message_summary="idle",
        )
        app.mqtt_notice_bridge = _FakeStatusBridge(
            mqtt_ok=False,
            last_error="",
            last_message_summary="idle",
        )
        return app

    @staticmethod
    def _label(item) -> str:
        return item.text(item) if callable(item.text) else item.text

    def test_build_menu_uses_grouped_hierarchy(self) -> None:
        app = self._make_app()

        with patch.object(self.tray_app, "read_runtime_config", return_value={}), patch.object(
            self.tray_app,
            "discover_serial_devices",
            return_value=[],
        ):
            menu = app._build_menu()
            top_labels = [self._label(item) for item in menu.items]
            self.assertEqual(
                top_labels,
                [
                    "idle | sessions 0 | running 0 | waiting 0",
                    "Hardware idle | port auto",
                    "Open BuddyParallel",
                    "Overview",
                    "Hardware",
                    "Settings & Tools",
                    "Quit",
                ],
            )

            overview_labels = [self._label(item) for item in menu.items[3].action.items]
            self.assertEqual(
                overview_labels,
                [
                    "No Claude connected",
                    "Weather off",
                    "Notice Telegram idle | idle",
                    "Controls | brightness ? | sound ? | led ?",
                    "Device | not connected",
                    "Battery | unavailable",
                ],
            )

            hardware_labels = [self._label(item) for item in menu.items[4].action.items]
            self.assertEqual(
                hardware_labels,
                [
                    "Refresh Status",
                    "Device | not connected",
                    "Battery | unavailable",
                    "Controls | brightness ? | sound ? | led ?",
                    "Brightness",
                    "LED Enabled",
                    "Sound Enabled",
                    "Pet",
                    "Serial Port",
                ],
            )

            system_labels = [self._label(item) for item in menu.items[5].action.items]
            self.assertEqual(
                system_labels,
                [
                    "Open Settings",
                    "Install Hooks",
                    "Logs & Files",
                    "Check Updates",
                    f"Version {self.tray_app.__version__}",
                ],
            )

            port_labels = [self._label(item) for item in menu.items[4].action.items[-1].action.items]
            self.assertEqual(port_labels, ["Auto Detect", "No serial ports found"])


if __name__ == "__main__":
    unittest.main()
