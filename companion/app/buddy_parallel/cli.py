from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="buddy-parallel")
    parser.add_argument(
        "command",
        nargs="?",
        default="run",
        choices=[
            "run",
            "headless",
            "status",
            "hooks",
            "feishu-helper",
            "settings",
            "dashboard",
            "setup",
            "flash-board",
            "packaging-notes",
        ],
    )
    parser.add_argument("--api-port", type=int, default=0)
    parser.add_argument("--port", default="")
    parser.add_argument("--firmware-dir", default="")
    parser.add_argument("--erase", action="store_true")
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
    if args.command == "setup":
        from buddy_parallel.ui.setup_window import main as setup_main

        setup_main()
        return
    if args.command == "flash-board":
        from buddy_parallel.services.board_setup import flash_board, save_board_port

        def progress(message: str) -> None:
            print(message, flush=True)

        try:
            result = flash_board(
                port=args.port,
                firmware_root=args.firmware_dir or None,
                erase_first=bool(args.erase),
                progress=progress,
            )
        except Exception as exc:
            raise SystemExit(str(exc)) from exc
        print(result.message)
        if result.ok:
            save_board_port(result.port)
        raise SystemExit(0 if result.ok else 1)
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
