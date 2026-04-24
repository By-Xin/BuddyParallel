from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class InstanceLockResult:
    acquired: bool
    reason: str = ""


class InstanceLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle = None

    def acquire(self) -> InstanceLockResult:
        if self._handle is not None:
            return InstanceLockResult(acquired=True)

        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self.path, "a+b")
        try:
            _lock_handle(handle)
        except OSError as exc:
            handle.close()
            return InstanceLockResult(acquired=False, reason=str(exc))

        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()).encode("utf-8"))
        handle.flush()
        self._handle = handle
        return InstanceLockResult(acquired=True)

    def release(self) -> None:
        handle = self._handle
        self._handle = None
        if handle is None:
            return
        try:
            _unlock_handle(handle)
        finally:
            handle.close()


def _lock_handle(handle) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_handle(handle) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        return

    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
