from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="buddy-parallel")
    parser.add_argument(
        "command",
        nargs="?",
        default="run",
        choices=["run", "headless", "status", "hooks", "feishu-helper", "settings", "dashboard", "packaging-notes"],
    )
    parser.add_argument("--api-port", type=int, default=0)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "feishu-helper":
        from buddy_parallel.services.feishu_helper import main as feishu_helper_main

        raise SystemExit(feishu_helper_main(api_port=args.api_port or None))
    if args.command == "settings":
        from buddy_parallel.ui.settings_window import main as settings_main

        settings_main()
        return
    if args.command == "dashboard":
        from buddy_parallel.ui.dashboard_window import main as dashboard_main

        dashboard_main()
        return
    if args.command == "packaging-notes":
        from buddy_parallel.services.packaging import build_notes

        print(build_notes())
        return

    from buddy_parallel.ui.tray_app import BuddyParallelApp

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
