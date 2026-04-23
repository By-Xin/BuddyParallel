from __future__ import annotations

import unittest

from buddy_parallel.core.aggregator import StateAggregator


class AggregatorTests(unittest.TestCase):
    def test_notice_queue_stays_until_dismissed_and_reports_total(self) -> None:
        aggregator = StateAggregator()
        aggregator.post_transient(
            message="Message 1",
            ttl_seconds=1,
            notice_id="n1",
            notice_from="B.Y.",
            notice_body="Hello there",
            notice_stamp="Apr 23",
        )
        aggregator.post_transient(
            message="Message 2",
            ttl_seconds=1,
            notice_id="n2",
            notice_from="B.Y.",
            notice_body="Second note",
            notice_stamp="Apr 23",
        )

        heartbeat = aggregator.build_heartbeat()

        self.assertEqual(heartbeat["notice"]["id"], "n1")
        self.assertEqual(heartbeat["notice"]["total"], 2)
        self.assertEqual(heartbeat["notice"]["index"], 1)

        self.assertTrue(aggregator.dismiss_notice("n1"))
        heartbeat = aggregator.build_heartbeat()

        self.assertEqual(heartbeat["notice"]["id"], "n2")
        self.assertEqual(heartbeat["notice"]["total"], 1)

    def test_prompt_forces_waiting_state(self) -> None:
        aggregator = StateAggregator()
        aggregator.apply_event(
            {
                "session_id": "abc",
                "state": "idle",
                "message": "Waiting for approval",
                "prompt": {"id": "req_1", "tool": "Edit", "hint": "Confirm"},
            }
        )

        heartbeat = aggregator.build_heartbeat()

        self.assertEqual(heartbeat["waiting"], 1)
        self.assertEqual(heartbeat["prompt"]["id"], "req_1")
        self.assertEqual(heartbeat["entries"][0], "approve: Edit")

    def test_weather_requires_board_summary(self) -> None:
        aggregator = StateAggregator()
        aggregator.set_weather({"location": "Singapore", "summary": "29C Rain"})
        self.assertIsNone(aggregator.build_heartbeat()["weather"])

        aggregator.set_weather({"location": "Singapore", "summary": "29C Rain", "board_summary": "29C Rain"})
        self.assertEqual(aggregator.build_heartbeat()["weather"]["board_summary"], "29C Rain")

    def test_clear_session_removes_idle_session(self) -> None:
        aggregator = StateAggregator()
        aggregator.apply_event(
            {
                "session_id": "vscode-demo",
                "state": "idle",
                "message": "Codex open",
            }
        )
        self.assertEqual(aggregator.build_heartbeat()["total"], 1)

        aggregator.apply_event(
            {
                "session_id": "vscode-demo",
                "clear_session": True,
            }
        )

        heartbeat = aggregator.build_heartbeat()
        self.assertEqual(heartbeat["total"], 0)
        self.assertEqual(heartbeat["msg"], "No Claude connected")


if __name__ == "__main__":
    unittest.main()
