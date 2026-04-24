from __future__ import annotations

import unittest
from pathlib import Path

from buddy_parallel.services.instance_lock import InstanceLock


class InstanceLockTests(unittest.TestCase):
    def test_second_lock_cannot_acquire_same_file(self) -> None:
        lock_path = Path(__file__).resolve().parents[2] / ".tmp-tests" / "instance-lock.test.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        if lock_path.exists():
            lock_path.unlink()

        first = InstanceLock(lock_path)
        second = InstanceLock(lock_path)
        first_result = first.acquire()
        second_result = second.acquire()

        self.assertTrue(first_result.acquired)
        self.assertFalse(second_result.acquired)

        first.release()
        third_result = second.acquire()
        self.assertTrue(third_result.acquired)
        second.release()

        if lock_path.exists():
            lock_path.unlink()


if __name__ == "__main__":
    unittest.main()
