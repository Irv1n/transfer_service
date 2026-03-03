from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict

_lock = threading.Lock()

def standards_file() -> Path:
    # project root: .../transfer_service/transfer_service/service/server.py -> parents[2] = .../transfer_service
    root = Path(__file__).resolve().parents[2]
    data_dir = root / "data"
    data_dir.mkdir(exist_ok=True)
    return data_dir / "standards.json"

def load_standards() -> Dict[str, Dict[str, Dict[str, Any]]]:
    path = standards_file()
    if not path.exists():
        return {"10V": {}, "1.018V": {}}
    with _lock:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

def save_standards(data: Dict[str, Dict[str, Dict[str, Any]]]) -> None:
    path = standards_file()
    with _lock:
        tmp = path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp.replace(path)

def get_standard(level: str, ref_id: str) -> Dict[str, Any]:
    data = load_standards()
    level_map = data.get(level) or {}
    std = level_map.get(ref_id)
    if not std:
        raise KeyError(f"Unknown standard {level}:{ref_id}")
    return std
