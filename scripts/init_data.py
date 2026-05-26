"""Initialize data/ from the project root reference files.

Run once before first start:
    python scripts/init_data.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def copy_if_missing(src: Path, dst: Path) -> bool:
    if not src.exists():
        print(f"[skip] source not found: {src}")
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        print(f"[keep] {dst} already exists")
        return False
    shutil.copy2(src, dst)
    print(f"[copy] {src.name} -> {dst}")
    return True


def main() -> int:
    copy_if_missing(ROOT / "guoyi_rooms_v2.json", DATA / "scenes" / "guoyi_rooms_v2.json")
    for sub in ("personas", "schedule_templates", "schedule_fragments", "actions"):
        (DATA / sub).mkdir(parents=True, exist_ok=True)
    print("data/ initialized.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
