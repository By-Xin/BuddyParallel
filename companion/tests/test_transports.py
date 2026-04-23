from __future__ import annotations

import unittest

from buddy_parallel.transports.base import UNSUPPORTED_TEXT_PLACEHOLDER, sanitize_device_payload, sanitize_device_text


class TransportSanitizationTests(unittest.TestCase):
    def test_ascii_text_passes_through(self) -> None:
        self.assertEqual(sanitize_device_text("Telegram: Hello"), "Telegram: Hello")

    def test_mixed_unicode_becomes_safe_ascii_with_cute_suffix(self) -> None:
        self.assertEqual(sanitize_device_text("你好 Claude"), "Claude ^_^ beep beep")

    def test_fully_unsupported_text_uses_placeholder(self) -> None:
        self.assertEqual(sanitize_device_text("你好"), UNSUPPORTED_TEXT_PLACEHOLDER)

    def test_payload_sanitizes_nested_strings(self) -> None:
        payload = {"msg": "天气", "entries": ["Hello", "世界"]}
        sanitized = sanitize_device_payload(payload)
        self.assertEqual(sanitized["msg"], UNSUPPORTED_TEXT_PLACEHOLDER)
        self.assertEqual(sanitized["entries"][0], "Hello")
        self.assertEqual(sanitized["entries"][1], UNSUPPORTED_TEXT_PLACEHOLDER)


if __name__ == "__main__":
    unittest.main()
