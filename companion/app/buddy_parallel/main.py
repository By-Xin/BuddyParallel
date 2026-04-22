from buddy_parallel.ui.tray_app import BuddyParallelApp


def main() -> None:
    BuddyParallelApp().run()


def run_headless() -> None:
    BuddyParallelApp(headless=True).run()


if __name__ == "__main__":
    main()
