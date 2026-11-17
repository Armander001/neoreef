"""Pipeline stages. Every stage exposes ``run(ctx, rs) -> rs``.

ORDER is the ``--stage all`` sequence. ``serve`` is not a data stage and is
started by the CLI after the data stages.
"""

from __future__ import annotations

from typing import Callable, Dict, List

from ..context import PipelineContext
from ..records import RecordSet
from . import cog, landuse, manifest, model3d, upload

StageFn = Callable[[PipelineContext, RecordSet], RecordSet]

ORDER: List[str] = ["cog", "landuse", "model3d", "upload", "manifest"]

STAGES: Dict[str, StageFn] = {
    "cog": cog.run,
    "landuse": landuse.run,
    "model3d": model3d.run,
    "upload": upload.run,
    "manifest": manifest.run,
}


def expand(stage: str) -> List[str]:
    """``all`` -> ORDER; a data stage -> itself; ``serve`` -> no data stages."""
    if stage == "all":
        return list(ORDER)
    if stage == "serve":
        return []
    if stage not in STAGES:
        raise KeyError(f"unknown stage {stage!r}; expected one of {['all', *ORDER, 'serve']}")
    return [stage]
