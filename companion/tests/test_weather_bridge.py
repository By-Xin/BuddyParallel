from __future__ import annotations

import unittest

from buddy_parallel.services.weather_bridge import WeatherBridge


class WeatherBridgeTests(unittest.TestCase):
    def test_pick_location_prefers_exact_match_over_population(self) -> None:
        results = [
            {"name": "Temasek", "population": 1_000_000, "latitude": 1.0, "longitude": 1.0, "timezone": "Asia/Singapore"},
            {"name": "Singapore", "population": 10_000, "latitude": 2.0, "longitude": 2.0, "timezone": "Asia/Singapore"},
        ]

        chosen = WeatherBridge._pick_location_result("Singapore", results)

        self.assertEqual(chosen["name"], "Singapore")

    def test_board_summary_is_temp_and_condition_only(self) -> None:
        self.assertEqual(WeatherBridge._build_board_summary(27, "Rain"), "27C Rain")

    def test_condition_label_maps_common_codes(self) -> None:
        self.assertEqual(WeatherBridge._condition_label(0), "Clear")
        self.assertEqual(WeatherBridge._condition_label(61), "Rain")
        self.assertEqual(WeatherBridge._condition_label(95), "Storm")


if __name__ == "__main__":
    unittest.main()
