"""Small filesystem helpers shared by the batch script and the pipeline."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Union

PathLike = Union[str, Path]


def ensure_dir(path: PathLike) -> Path:
    """``mkdir -p`` and return the Path."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def safe_unlink(path: PathLike) -> bool:
    """Delete a file if present; never raises. Returns True if removed."""
    p = Path(path)
    try:
        if p.is_file():
            p.unlink()
            return True
    except OSError:
        pass
    return False


def copy_tree(src: PathLike, dst: PathLike) -> Path:
    """Copy a directory tree, overwriting existing files (Python 3.8+ safe)."""
    src, dst = Path(src), Path(dst)
    shutil.copytree(str(src), str(dst), dirs_exist_ok=True)
    return dst
