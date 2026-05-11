from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any


def now_ts() -> float:
    return time.time()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ensure_file_from_example(target: Path, example: Path) -> None:
    """Create a local mutable config from the tracked example on first start."""
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(example, target)
