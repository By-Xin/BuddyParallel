from __future__ import annotations

from buddy_parallel.runtime.config import ConfigStore
from buddy_parallel.runtime.logging_utils import configure_logging
from buddy_parallel.runtime.state import StateStore


class BuddyParallelApp:
    def __init__(self) -> None:
        self.logger = configure_logging()
        self.config_store = ConfigStore()
        self.state_store = StateStore()

    def run(self) -> None:
        config = self.config_store.load()
        state = self.state_store.load()
        self.logger.info("BuddyParallel bootstrap starting")
        self.logger.info("transport_mode=%s device_name=%s last_status=%s", config.transport_mode, config.device_name, state.last_status)
        print("BuddyParallel companion bootstrap is ready.")
