from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from buddy_parallel.ui.settings_window import main


if __name__ == "__main__":
    main()
