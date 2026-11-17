"""Persist the RecordSet between stage runs.

``<CESIUM_OUTPUT_DIR>/.state/records.json`` is written after every stage and
read before the next one, so ``--stage manifest`` run on its own sees exactly
what ``--stage cog`` produced (types, bboxes, ion ids) instead of re-scanning
disk and guessing.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from .records import RecordSet

STATE_DIR = ".state"
RECORDS_FILE = "records.json"


def state_path(out_dir: Path) -> Path:
    return Path(out_dir) / STATE_DIR / RECORDS_FILE


def save_records(out_dir: Path, rs: RecordSet) -> Path:
    p = state_path(out_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rs.to_dict(), f, indent=2, ensure_ascii=False)
    tmp.replace(p)
    return p


def load_records(out_dir: Path, log: Optional[logging.Logger] = None) -> RecordSet:
    """Return the saved RecordSet, or an empty one if none exists / it is unreadable."""
    p = state_path(out_dir)
    if not p.exists():
        return RecordSet()
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        rs = RecordSet.from_dict(data)
        if log:
            log.info(f"Loaded state: {len(rs.orthos)} ortho, {len(rs.landuse)} landuse, "
                     f"{len(rs.models)} model record(s) from {p}")
        return rs
    except Exception as e:  # corrupt / schema mismatch: start fresh rather than abort
        if log:
            log.warning(f"Could not read {p} ({e}); starting with empty records")
        return RecordSet()


def clear_records(out_dir: Path) -> None:
    p = state_path(out_dir)
    if p.exists():
        p.unlink()
