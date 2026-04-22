from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from buddy_parallel.runtime.config import STATE_PATH


@dataclass
class RuntimeState:
    last_transport: str = ""
    last_device_id: str = ""
    last_status: str = "bootstrap"
    last_error: str = ""


class StateStore:
    def __init__(self, path: Path = STATE_PATH):
        self.path = path

    def load(self) -> RuntimeState:
        if not self.path.exists():
            return RuntimeState()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return RuntimeState(**{**asdict(RuntimeState()), **data})

    def save(self, state: RuntimeState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(asdict(state), ensure_ascii=False, indent=2), encoding="utf-8")
