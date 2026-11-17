"""Stage ``manifest``: write manifest.json + tochicd_legend.json and copy the viewers."""

from __future__ import annotations

import json
from pathlib import Path

from neoreef.common.fs import copy_tree
from neoreef.common.landuse_codes import legend_entries
from ..context import PipelineContext
from ..manifest_schema import LEGEND_FILENAME, MANIFEST_FILENAME, build_manifest
from ..records import RecordSet


def write_legend(out_dir: Path) -> Path:
    p = out_dir / LEGEND_FILENAME
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"schema_version": 1, "entries": legend_entries()}, f, indent=2, ensure_ascii=False)
    return p


def copy_viewers(ctx: PipelineContext) -> int:
    """Copy the viewer pages (and their css/js) next to manifest.json. Returns file count."""
    log = ctx.log
    if ctx.viewers_dir and (ctx.viewers_dir / "index.html").exists():
        copy_tree(ctx.viewers_dir, ctx.out_dir)
        n = sum(1 for p in ctx.viewers_dir.rglob("*") if p.is_file())
        log.info(f"Viewers copied from {ctx.viewers_dir} ({n} file(s))")
        return n
    log.warning("No viewers found to copy (set VIEWERS_DIR in config, NEOREEF_VIEWERS_DIR, "
                "or --viewers-dir; expected a directory containing index.html)")
    return 0


def run(ctx: PipelineContext, rs: RecordSet) -> RecordSet:
    log = ctx.log
    log.info("--- Stage: write manifest ---")
    ctx.out_dir.mkdir(parents=True, exist_ok=True)

    manifest = build_manifest(rs, ctx.cfg)
    out = ctx.out_dir / MANIFEST_FILENAME
    with open(out, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    log.info(f"Manifest written: {out}  (schema v{manifest['schema_version']}, "
             f"{len(manifest['orthomosaics'])} ortho, {len(manifest['landuse_layers'])} landuse, "
             f"{len(manifest['models_3d'])} model)")
    if ctx.cfg.base_ion_3dtiles_asset is not None:
        log.info(f"  Base 3D tiles asset: {ctx.cfg.base_ion_3dtiles_asset}")
    if ctx.cfg.base_ion_imagery_asset is not None:
        log.info(f"  Base imagery asset: {ctx.cfg.base_ion_imagery_asset}")

    log.info(f"Legend written: {write_legend(ctx.out_dir)}")
    copy_viewers(ctx)
    log.info(f"Open viewer at: http://localhost:{ctx.port}/  (run --stage serve first)")
    rs.mark("manifest")
    return rs
