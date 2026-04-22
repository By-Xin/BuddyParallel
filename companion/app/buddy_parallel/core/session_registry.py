from __future__ import annotations

from dataclasses import dataclass, field
from time import time


@dataclass
class SessionSnapshot:
    session_id: str
    state: str = "idle"
    message: str = ""
    running: bool = False
    waiting: bool = False
    updated_at: float = field(default_factory=time)
    entries: list[str] = field(default_factory=list)
