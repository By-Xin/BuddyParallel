from __future__ import annotations

import unittest

from buddy_parallel.services.packaging import build_notes


class PackagingNotesTests(unittest.TestCase):
    def test_build_notes_mentions_release_shape(self) -> None:
        notes = build_notes()
        self.assertIn("BuddyParallel packaging notes", notes)
        self.assertIn("buddy-parallel", notes)
        self.assertIn("Release checklist", notes)


if __name__ == "__main__":
    unittest.main()
