"""Run the desktop app with uv run main.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from ut_past_grades import main

if __name__ == "__main__":
    main()
