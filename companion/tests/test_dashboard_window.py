from __future__ import annotations

import unittest

from buddy_parallel.runtime.config import AppConfig
from buddy_parallel.runtime.state import RuntimeState
from buddy_parallel.ui.dashboard_window import build_dashboard_model


class DashboardWindowTests(unittest.TestCase):
    def test_build_dashboard_model_formats_live_runtime_and_mqtt_state(self) -> None:
        config = AppConfig(
            transport_mode="serial",
            serial_port="COM7",
            notice_transport="mqtt",
            weather_enabled=True,
            weather_location_query="Singapore",
            auto_start=True,
            api_server_port=43112,
            hook_server_port=43111,
        )
        runtime = {
            "transport": "serial",
            "device_port": "COM7",
            "heartbeat": {
                "total": 3,
                "running": 1,
                "waiting": 2,
                "msg": "Review in progress",
            },
            "device_status": {
                "data": {
                    "name": "Desk Buddy",
                    "bat": {"pct": 91, "usb": True},
                    "settings": {"brightness": 3, "sound": True, "led": False},
                    "pet": {"name": "duck"},
                }
            },
        }
        state = RuntimeState(
            weather_location_name="Singapore",
            last_weather_summary="31C Cloudy",
            mqtt_connected=True,
            last_mqtt_message_summary="2 notices delivered",
        )

        model = build_dashboard_model(config, runtime, state)

        self.assertEqual(model.status_badge, "Live")
        self.assertIn("Transport: serial", model.runtime_lines)
        self.assertIn("Device: Desk Buddy", model.hardware_lines)
        self.assertIn("Pet: Duck", model.hardware_lines)
        self.assertIn("Notice: MQTT active | 2 notices delivered", model.service_lines)
        self.assertIn("Weather: Singapore | 31C Cloudy", model.service_lines)
        self.assertIn("Launch at startup: on", model.setup_lines)

    def test_build_dashboard_model_formats_idle_state(self) -> None:
        config = AppConfig(weather_enabled=False, notice_transport="telegram")
        model = build_dashboard_model(config, {}, RuntimeState())

        self.assertEqual(model.status_badge, "Idle")
        self.assertIn("Device: not connected", model.hardware_lines)
        self.assertIn("Notice: Telegram idle", model.service_lines)
        self.assertIn("Weather: off", model.service_lines)

    def test_build_dashboard_model_formats_notice_off(self) -> None:
        model = build_dashboard_model(AppConfig(), {}, RuntimeState(last_telegram_error="old error"))

        self.assertIn("Notice: off", model.service_lines)
        self.assertIn("Notice source: off", model.setup_lines)


if __name__ == "__main__":
    unittest.main()
