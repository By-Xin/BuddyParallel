from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from pathlib import Path

from buddy_parallel.runtime.config import STATE_PATH


@dataclass
class RuntimeState:
    last_transport: str = ""
    last_device_id: str = ""
    last_status: str = "bootstrap"
    last_error: str = ""
    telegram_offset: int | None = None
    last_telegram_error: str = ""
    last_telegram_message_summary: str = "idle"
    last_telegram_delivery_at: float = 0.0


class StateStore:
    def __init__(self, path: Path = STATE_PATH):
        self.path = path
        self._lock = threading.Lock()

    def load(self) -> RuntimeState:
        with self._lock:
            if not self.path.exists():
                return RuntimeState()
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return RuntimeState(**{**asdict(RuntimeState()), **data})

    def save(self, state: RuntimeState) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(asdict(state), ensure_ascii=False, indent=2), encoding="utf-8")

    def update(self, **kwargs) -> RuntimeState:
        state = self.load()
        for key, value in kwargs.items():
            setattr(state, key, value)
        self.save(state)
        return state
