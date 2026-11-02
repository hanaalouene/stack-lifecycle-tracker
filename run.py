"""Convenience launcher: python run.py run [--no-email] [--days 180]"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from versionwatch.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
