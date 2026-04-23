from __future__ import annotations

import unittest

from buddy_parallel.core.hardware_state import (
    GIF_PET_INDEX,
    HardwareSnapshot,
    brightness_display,
    parse_hardware_snapshot,
    pet_choices,
    pet_display_name,
)


class HardwareStateTests(unittest.TestCase):
    def test_parse_status_payload_extracts_controls_and_pet(self) -> None:
        snapshot = parse_hardware_snapshot(
            {
                "ack": "status",
                "ok": True,
                "data": {
                    "name": "BuddyParallel",
                    "owner": "Xin",
                    "bat": {"pct": 82, "usb": True},
                    "settings": {"brightness": 3, "sound": True, "led": False},
                    "pet": {"mode": "ascii", "index": 3, "name": "blob", "gif_available": True},
                },
            }
        )

        self.assertEqual(
            snapshot,
            HardwareSnapshot(
                connected=True,
                name="BuddyParallel",
                owner="Xin",
                battery_pct=82,
                usb_powered=True,
                brightness=3,
                sound_enabled=True,
                led_enabled=False,
                pet_index=3,
                pet_name="blob",
                pet_mode="ascii",
                gif_available=True,
            ),
        )

    def test_parse_status_payload_derives_gif_pet_index(self) -> None:
        snapshot = parse_hardware_snapshot(
            {
                "data": {
                    "settings": {"brightness": "4"},
                    "pet": {"mode": "gif", "gif_available": 1},
                }
            }
        )

        self.assertEqual(snapshot.pet_index, GIF_PET_INDEX)
        self.assertEqual(snapshot.pet_name, "gif")
        self.assertTrue(snapshot.gif_available)
        self.assertEqual(brightness_display(snapshot.brightness), "4/4")

    def test_pet_choices_include_gif_only_when_available(self) -> None:
        without_gif = pet_choices(HardwareSnapshot())
        with_gif = pet_choices(HardwareSnapshot(gif_available=True))

        self.assertEqual(without_gif[-1][1], "Chonk")
        self.assertEqual(with_gif[-2][1], "Chonk")
        self.assertEqual(with_gif[-1], (GIF_PET_INDEX, "GIF Character"))

    def test_pet_display_name_formats_for_humans(self) -> None:
        self.assertEqual(pet_display_name("axolotl"), "Axolotl")
        self.assertEqual(pet_display_name("gif"), "GIF Character")


if __name__ == "__main__":
    unittest.main()
