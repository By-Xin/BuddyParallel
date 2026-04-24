from __future__ import annotations

import unittest

from buddy_parallel.runtime.config import AppConfig, parse_month_day, validate_config


class AppConfigTests(unittest.TestCase):
    def test_parse_month_day_accepts_short_and_full_dates(self) -> None:
        self.assertEqual(parse_month_day("04-24"), (4, 24))
        self.assertEqual(parse_month_day("2026-12-25"), (12, 25))

    def test_validate_config_rejects_invalid_birthday(self) -> None:
        with self.assertRaisesRegex(ValueError, "birthday_mmdd"):
            validate_config(AppConfig(birthday_mmdd="13-99"))

    def test_default_notice_transport_is_off(self) -> None:
        config = validate_config(AppConfig())

        self.assertEqual(config.notice_transport, "off")


if __name__ == "__main__":
    unittest.main()
