"""Shareable JPEG preview of the orthomosaic."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

Log = Callable[[str], None]


def export_jpeg_preview(chunk, jpeg_path: Path, jpeg_quality: int, log: Log) -> Optional[Path]:
    """Export the orthomosaic as JPEG; returns the written path or None.

    Attempt 1: direct export. Attempt 2: ``white_background=True`` to a
    ``*_render.jpg`` sibling, which resolves some projection edge cases in
    non-georeferenced projects. No world file is written either way.
    """
    import Metashape
    jpeg_path = Path(jpeg_path)
    common = dict(image_format=Metashape.ImageFormatJPEG, jpeg_quality=jpeg_quality,
                  write_kml=False, world_file=False)
    try:
        chunk.exportOrthomosaic(str(jpeg_path), **common)
        log(f"    [OK] JPEG preview saved: {jpeg_path}")
        return jpeg_path
    except Exception as e1:
        log(f"    WARNING: JPEG export attempt 1 failed ({e1}); trying fallback...")

    fallback = jpeg_path.with_name(jpeg_path.stem + "_render" + jpeg_path.suffix)
    try:
        chunk.exportOrthomosaic(str(fallback), white_background=True, **common)
        log(f"    [OK] JPEG fallback saved: {fallback}")
        return fallback
    except Exception as e2:
        log(f"    WARNING: JPEG export attempt 2 also failed ({e2}). No JPEG preview for this survey.")
        return None
