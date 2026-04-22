from __future__ import annotations

import argparse

from buddy_parallel.ui.tray_app import BuddyParallelApp


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="buddy-parallel")
    parser.add_argument("command", nargs="?", default="run", choices=["run", "headless", "status", "hooks"])
    return parser


def main() -> None:
    args = build_parser().parse_args()
    app = BuddyParallelApp(headless=args.command == "headless")
    if args.command in {"run", "headless"}:
        app.run()
        return
    if args.command == "status":
        print(app.snapshot())
        return
    if args.command == "hooks":
        app.install_hooks()
        return


if __name__ == "__main__":
    main()
