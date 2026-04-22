from __future__ import annotations

from buddy_parallel.core.companion_runtime import CompanionRuntime
from buddy_parallel.runtime.config import ConfigStore
from buddy_parallel.runtime.logging_utils import configure_logging
from buddy_parallel.runtime.state import StateStore


class BuddyParallelApp:
    def __init__(self, headless: bool = False) -> None:
        self.headless = headless
        self.logger = configure_logging()
        self.config_store = ConfigStore()
        self.state_store = StateStore()

    def run(self) -> None:
        config = self.config_store.load()
        state = self.state_store.load()
        self.logger.info("BuddyParallel starting")
        self.logger.info(
            "transport_mode=%s device_name=%s last_status=%s",
            config.transport_mode,
            config.device_name,
            state.last_status,
        )
        runtime = CompanionRuntime(config=config, state_store=self.state_store)
        if self.headless:
            print("BuddyParallel companion running in headless mode.")
        else:
            print("BuddyParallel tray shell not implemented yet; running shared runtime in foreground.")
        runtime.run_forever()

    def snapshot(self) -> dict:
        config = self.config_store.load()
        runtime = CompanionRuntime(config=config, state_store=self.state_store)
        return runtime.snapshot()

    def install_hooks(self) -> None:
        from buddy_parallel.ingest.install_hooks import main as install_main

        install_main()
