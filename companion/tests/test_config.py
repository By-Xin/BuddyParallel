from __future__ import annotations

import json
import shutil
import unittest
import uuid
from pathlib import Path

from buddy_parallel.runtime.config import AppConfig, ConfigStore, parse_month_day, validate_config


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

    def test_config_store_ignores_removed_beta_fields(self) -> None:
        root = Path(__file__).resolve().parents[1] / "tmp-config-tests" / f"case-{uuid.uuid4().hex}"
        root.mkdir(parents=True, exist_ok=True)
        try:
            path = root / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "transport_mode": "serial",
                        "serial_port": "COM7",
                        "board_profile": "m5stickc-plus",
                    }
                ),
                encoding="utf-8",
            )

            config = ConfigStore(path).load()
        finally:
            shutil.rmtree(root, ignore_errors=True)

        self.assertEqual(config.transport_mode, "serial")
        self.assertEqual(config.serial_port, "COM7")


if __name__ == "__main__":
    unittest.main()
