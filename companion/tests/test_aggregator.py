from __future__ import annotations

import unittest
from datetime import date

from buddy_parallel.core.aggregator import StateAggregator
from buddy_parallel.core.event_mapper import normalize_event
from buddy_parallel.runtime.config import AppConfig


class AggregatorCompletionTests(unittest.TestCase):
    def test_notification_with_explicit_completed_false_does_not_pulse_celebration(self) -> None:
        aggregator = StateAggregator()
        aggregator.apply_event(
            normalize_event(
                {
                    "event": "Notification",
                    "session_id": "vscode-window",
                    "session_title": "VS Code",
                    "message": "VS Code: denied workspace edit",
                    "completed": False,
                }
            )
        )

        heartbeat = aggregator.build_heartbeat()
        self.assertFalse(heartbeat["completed"])
        self.assertEqual(heartbeat["msg"], "VS Code: denied workspace edit")

    def test_notification_defaults_to_completed_when_not_overridden(self) -> None:
        aggregator = StateAggregator()
        aggregator.apply_event(
            normalize_event(
                {
                    "event": "Notification",
                    "session_id": "claude-default",
                    "session_title": "Claude Code",
                    "message": "Claude Code: notification",
                }
            )
        )

        heartbeat = aggregator.build_heartbeat()
        self.assertTrue(heartbeat["completed"])

    def test_vscode_approval_notifications_do_not_pulse_completed_for_allow_or_deny(self) -> None:
        for message in [
            "VS Code: approved workspace edit",
            "VS Code: denied workspace edit",
        ]:
            with self.subTest(message=message):
                aggregator = StateAggregator()
                aggregator.apply_event(
                    normalize_event(
                        {
                            "event": "Notification",
                            "session_id": "vscode-window",
                            "session_title": "VS Code",
                            "message": message,
                            "completed": False,
                        }
                    )
                )

                heartbeat = aggregator.build_heartbeat()
                self.assertFalse(heartbeat["completed"])
                self.assertEqual(heartbeat["msg"], message)

    def test_vscode_run_failure_sequence_does_not_pulse_completed(self) -> None:
        aggregator = StateAggregator()
        aggregator.apply_event(
            normalize_event(
                {
                    "event": "PreToolUse",
                    "session_id": "vscode-window-run",
                    "session_title": "Run",
                    "message": "Run: python fail.py",
                    "running": True,
                }
            )
        )
        heartbeat = aggregator.build_heartbeat()
        self.assertFalse(heartbeat["completed"])
        self.assertEqual(heartbeat["msg"], "Run: python fail.py")

        aggregator.apply_event(
            normalize_event(
                {
                    "event": "Notification",
                    "session_id": "vscode-window",
                    "session_title": "VS Code",
                    "message": "Run failed",
                    "entries": ["python fail.py", "exit 1"],
                    "completed": False,
                }
            )
        )
        heartbeat = aggregator.build_heartbeat()
        self.assertFalse(heartbeat["completed"])
        self.assertIn("Run failed", heartbeat["entries"])

        aggregator.apply_event(
            normalize_event(
                {
                    "session_id": "vscode-window-run",
                    "session_title": "Run",
                    "clear_session": True,
                    "state": "idle",
                }
            )
        )
        heartbeat = aggregator.build_heartbeat()
        self.assertFalse(heartbeat["completed"])
        self.assertEqual(heartbeat["msg"], "Run failed")

    def test_problems_attention_and_clear_do_not_pulse_completed(self) -> None:
        aggregator = StateAggregator()
        aggregator.apply_event(
            normalize_event(
                {
                    "event": "PostCompact",
                    "session_id": "vscode-window-problems",
                    "session_title": "Problems",
                    "message": "Problems: 2 errors",
                    "entries": ["2 errors", "1 warning"],
                }
            )
        )
        heartbeat = aggregator.build_heartbeat()
        self.assertFalse(heartbeat["completed"])
        self.assertEqual(heartbeat["msg"], "Problems: 2 errors")

        aggregator.apply_event(
            normalize_event(
                {
                    "session_id": "vscode-window-problems",
                    "session_title": "Problems",
                    "clear_session": True,
                    "state": "idle",
                }
            )
        )
        heartbeat = aggregator.build_heartbeat()
        self.assertFalse(heartbeat["completed"])

    def test_birthday_theme_takes_over_when_everything_is_idle(self) -> None:
        aggregator = StateAggregator(
            config=AppConfig(
                festive_themes_enabled=True,
                birthday_mmdd="04-24",
                birthday_name="Xin",
            )
        )

        heartbeat = aggregator.build_heartbeat(today=date(2026, 4, 24))

        self.assertFalse(heartbeat["completed"])
        self.assertEqual(heartbeat["msg"], "No Claude connected")
        self.assertEqual(heartbeat["theme"]["key"], "birthday")
        self.assertEqual(heartbeat["theme"]["title"], "Happy")
        self.assertEqual(heartbeat["theme"]["subtitle"], "Birthday")
        self.assertIn("Xin", heartbeat["theme"]["detail"])

    def test_birthday_theme_is_a_daily_pulse_not_a_repeating_screensaver(self) -> None:
        aggregator = StateAggregator(
            config=AppConfig(
                festive_themes_enabled=True,
                birthday_mmdd="04-24",
                birthday_name="Xin",
            )
        )

        first = aggregator.build_heartbeat(today=date(2026, 4, 24))
        second = aggregator.build_heartbeat(today=date(2026, 4, 24))

        self.assertEqual(first["theme"]["key"], "birthday")
        self.assertIsNone(second["theme"])

    def test_christmas_theme_does_not_override_active_work(self) -> None:
        aggregator = StateAggregator(config=AppConfig(festive_themes_enabled=True))
        aggregator.apply_event(
            normalize_event(
                {
                    "event": "PreToolUse",
                    "session_id": "claude-default",
                    "session_title": "Claude Code",
                    "message": "Claude Code: working",
                    "running": True,
                }
            )
        )

        heartbeat = aggregator.build_heartbeat(today=date(2026, 12, 25))

        self.assertFalse(heartbeat["completed"])
        self.assertEqual(heartbeat["msg"], "Claude Code: working")
        self.assertEqual(heartbeat["theme"]["key"], "christmas")


if __name__ == "__main__":
    unittest.main()
