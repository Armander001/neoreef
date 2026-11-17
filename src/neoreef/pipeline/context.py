"""PipelineContext: everything a stage needs, built once by the CLI."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .config import PipelineConfig

#: Repo root when running from a checkout (src/neoreef/pipeline/context.py -> ../../..).
PACKAGE_ROOT = Path(__file__).resolve().parents[3]

COG_SUBDIR = "cogs"
PREVIEW_SUBDIR = "previews"
LANDUSE_SUBDIR = "landuse"
MODELS_SUBDIR = "models"


def resolve_viewers_dir(cfg: PipelineConfig) -> Optional[Path]:
    """Directory holding the viewer pages to copy next to manifest.json.

    Order: ``VIEWERS_DIR`` in config / ``NEOREEF_VIEWERS_DIR`` env, then
    ``<repo>/viewers``. Returns None if nothing suitable exists.
    """
    candidates = []
    if cfg.viewers_dir:
        candidates.append(cfg.viewers_dir)
    candidates.append(PACKAGE_ROOT / "viewers")
    for c in candidates:
        if c.is_dir():
            return c
    return None


@dataclass
class PipelineContext:
    cfg: PipelineConfig
    log: logging.Logger
    out_dir: Path
    viewers_dir: Optional[Path] = None
    port: int = 8765

    @property
    def cog_dir(self) -> Path:
        return self.out_dir / COG_SUBDIR

    @property
    def preview_dir(self) -> Path:
        return self.out_dir / PREVIEW_SUBDIR

    @property
    def landuse_out_dir(self) -> Path:
        return self.out_dir / LANDUSE_SUBDIR

    @property
    def models_out_dir(self) -> Path:
        return self.out_dir / MODELS_SUBDIR

    @property
    def continue_on_error(self) -> bool:
        return self.cfg.continue_on_error
