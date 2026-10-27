"""Simulate new historian files arriving: move the next N days from data/incoming to data/raw.

    uv run python tools/arrival.py        # 1 day arrives
    uv run python tools/arrival.py 3      # 3 days arrive
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    incoming = sorted((ROOT / "data" / "incoming" / "historian").glob("date=*"))
    if not incoming:
        print("No files left to arrive: they have all arrived.")
        return
    for src in incoming[:n]:
        dst = ROOT / "data" / "raw" / "historian" / src.name
        shutil.move(str(src), str(dst))
        print(f"Arrived {src.name}  ->  data/raw/historian/")
    print(f"{max(len(incoming) - n, 0)} days left to arrive.")


if __name__ == "__main__":
    main()
