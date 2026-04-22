from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass
class TransportBase:
    name: str

    def available(self) -> bool:
        return False

    def send_json(self, payload: dict) -> None:
        self.send_line(json.dumps(payload, ensure_ascii=False) + "\n")

    def send_line(self, line: str) -> None:
        raise NotImplementedError
