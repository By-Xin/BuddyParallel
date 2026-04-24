from buddy_parallel.cli import main as cli_main


def main() -> None:
    cli_main()


def run_headless() -> None:
    from buddy_parallel.ui.tray_app import BuddyParallelApp

    BuddyParallelApp(headless=True).run()


if __name__ == "__main__":
    main()
