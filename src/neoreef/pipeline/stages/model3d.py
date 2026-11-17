"""Stage ``model3d``: collect 3D Tiles / glTF models and place them on the globe.

Metashape exports underwater surveys in a local frame with no georeference.
A tileset only becomes visible once ``root.transform`` maps that frame onto
the Earth, so this stage injects the transform computed from the survey's
hand-entered position (``survey_positions.json``). Models without a known
position are still copied and listed, but flagged ``placed=false`` so the
viewer does not render them at Earth's centre.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional

from neoreef.common.geodesy import enu_to_ecef_matrix
from neoreef.common.naming import MODEL_GLB_SUFFIX, TILESET_FILENAME
from ..context import PipelineContext
from ..records import Model3DRecord, RecordSet, carry_over

GLTF_EXTS = (".glb", ".gltf")


def normalize_position(pos: Optional[Dict]) -> Optional[Dict[str, float]]:
    if not pos or "lon" not in pos or "lat" not in pos:
        return None
    return {
        "lon": float(pos["lon"]),
        "lat": float(pos["lat"]),
        "height": float(pos.get("height", 0.0) or 0.0),
        "heading_deg": float(pos.get("heading_deg", pos.get("heading", 0.0)) or 0.0),
    }


def inject_transform(tileset_path: Path, position: Optional[Dict[str, float]]) -> bool:
    """Write ``root.transform`` for *position*; return whether the tileset is placed."""
    with open(tileset_path, encoding="utf-8") as f:
        tileset = json.load(f)
    root = tileset.setdefault("root", {})
    if position is None:
        return "transform" in root
    root["transform"] = enu_to_ecef_matrix(position["lon"], position["lat"],
                                           position["height"], position["heading_deg"])
    with open(tileset_path, "w", encoding="utf-8") as f:
        json.dump(tileset, f, indent=2)
    return True


def _survey_key(name: str) -> str:
    """``X_compressed`` (glb stem) -> ``X`` so a position keyed by survey matches."""
    stem_suffix = MODEL_GLB_SUFFIX[:-len(".glb")]
    return name[:-len(stem_suffix)] if name.endswith(stem_suffix) else name


def scan_models(ctx: PipelineContext) -> List[Model3DRecord]:
    cfg, log = ctx.cfg, ctx.log
    records: List[Model3DRecord] = []
    base = cfg.models_3d_dir
    out = ctx.models_out_dir

    if base and base.exists():
        out.mkdir(parents=True, exist_ok=True)
        tilesets = sorted(base.rglob(TILESET_FILENAME))
        tileset_dirs = {ts.parent for ts in tilesets}

        for ts in tilesets:
            survey = ts.parent.name
            dst_dir = out / survey
            if not (dst_dir / TILESET_FILENAME).exists():
                shutil.copytree(str(ts.parent), str(dst_dir), dirs_exist_ok=True)
                log.info(f"  3D Tiles copied: {survey}/")
            records.append(Model3DRecord(survey_name=survey, model_type="mesh", src_path=ts,
                                         format="3dtiles", output_path=dst_dir / TILESET_FILENAME))

        for ext in GLTF_EXTS:
            for f in sorted(base.rglob("*" + ext)):
                if f.parent in tileset_dirs:
                    continue  # the tileset's own content, not a standalone model
                dst = out / f.name
                if not dst.exists():
                    shutil.copy2(str(f), str(dst))
                    log.info(f"  3D model copied: {f.name}")
                records.append(Model3DRecord(survey_name=_survey_key(f.stem), model_type="mesh",
                                             src_path=f, format=ext[1:], output_path=dst))
    elif base:
        log.warning(f"MODELS_3D_DIR does not exist: {base}")

    for entry in cfg.extra_3d_models:
        p = Path(entry["path"])
        if not p.exists():
            log.warning(f"  EXTRA_3D_MODEL not found: {p}")
            continue
        fmt = entry.get("format") or ("3dtiles" if p.name == TILESET_FILENAME else p.suffix.lstrip("."))
        records.append(Model3DRecord(
            survey_name=entry.get("survey_name", p.parent.name if fmt == "3dtiles" else p.stem),
            model_type=entry.get("model_type", "mesh"), src_path=p, format=fmt,
            output_path=p, position=normalize_position(entry.get("position")),
        ))
        log.info(f"  Added extra 3D model: {records[-1].survey_name}")

    log.info(f"Found {len(records)} 3D model(s)")
    return records


def run(ctx: PipelineContext, rs: RecordSet) -> RecordSet:
    log = ctx.log
    log.info("--- Stage: 3D models ---")
    records = scan_models(ctx)
    carry_over(rs.models, records, ("ion_asset_id",))

    for rec in records:
        pos = rec.position or normalize_position(ctx.cfg.survey_positions.get(rec.survey_name))
        rec.position = pos
        if rec.format == "3dtiles" and rec.output_path and rec.output_path.exists():
            try:
                rec.placed = inject_transform(rec.output_path, pos)
            except Exception as e:
                log.error(f"  {rec.id}: could not update tileset.json ({e})")
                rec.placed = False
        else:
            rec.placed = pos is not None
        if not rec.placed:
            log.warning(f"  {rec.id}: no position known; add '{rec.survey_name}' to "
                        f"survey_positions.json or the viewer will skip it")

    rs.models = records
    rs.mark("model3d")
    return rs
