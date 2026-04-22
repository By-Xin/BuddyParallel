from __future__ import annotations

from buddy_parallel.runtime.config import ConfigStore


def main() -> None:
    config = ConfigStore().load()
    print("BuddyParallel settings placeholder")
    print(f"transport_mode={config.transport_mode}")
    print(f"device_name={config.device_name}")


if __name__ == "__main__":
    main()
