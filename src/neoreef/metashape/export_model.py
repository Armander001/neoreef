"""3D model export for CesiumJS:  OBJ -> glb (obj2gltf) -> compressed glb (gltfpack) -> tileset.json.

Also writes ``survey_meta.json`` next to the tileset so the Cesium pipeline
knows the model is in a local frame (no CRS) and needs a globe transform.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional

from neoreef import __version__
from neoreef.common.fs import safe_unlink
from neoreef.common.naming import SURVEY_META_FILENAME, TILESET_FILENAME, model_glb_filename
from .config import MetashapeConfig

Log = Callable[[str], None]
BBox = Dict[str, float]


def run_tool(cmd_args: List[str], log: Log, label: str = "tool", timeout: int = 600) -> bool:
    """Run an external command, log its output, return True on exit code 0."""
    try:
        result = subprocess.run(cmd_args, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        log(f"    WARNING: {label} not found on PATH - install it or set the full path in config")
        return False
    except subprocess.TimeoutExpired:
        log(f"    WARNING: {label} timed out after {timeout}s")
        return False
    if result.returncode == 0:
        if result.stdout.strip():
            log(f"      {label} stdout: {result.stdout.strip()}")
        return True
    log(f"    WARNING: {label} failed (exit {result.returncode})")
    if result.stderr.strip():
        log(f"      stderr: {result.stderr.strip()}")
    return False


def compute_model_bbox(chunk) -> BBox:
    """Axis-aligned bounds of the chunk's mesh in its local frame (single pass)."""
    model = chunk.model
    if not model or not model.vertices:
        raise ValueError("Chunk has no model vertices")
    it = iter(model.vertices)
    first = next(it).coord
    x_min = x_max = first.x
    y_min = y_max = first.y
    z_min = z_max = first.z
    for v in it:
        c = v.coord
        if c.x < x_min: x_min = c.x
        elif c.x > x_max: x_max = c.x
        if c.y < y_min: y_min = c.y
        elif c.y > y_max: y_max = c.y
        if c.z < z_min: z_min = c.z
        elif c.z > z_max: z_max = c.z
    return {"x_min": x_min, "x_max": x_max, "y_min": y_min, "y_max": y_max, "z_min": z_min, "z_max": z_max}


def make_tileset(glb_filename: str, bbox: BBox) -> dict:
    """3D Tiles 1.1 tileset for one glb, bounded by a local-origin box.

    No ``root.transform`` is written here: the Cesium pipeline injects it from
    the survey's configured position (see neoreef.pipeline.stages.model3d).
    """
    dx = (bbox["x_max"] - bbox["x_min"]) / 2.0
    dy = (bbox["y_max"] - bbox["y_min"]) / 2.0
    dz = (bbox["z_max"] - bbox["z_min"]) / 2.0
    cx = (bbox["x_min"] + bbox["x_max"]) / 2.0
    cy = (bbox["y_min"] + bbox["y_max"]) / 2.0
    cz = (bbox["z_min"] + bbox["z_max"]) / 2.0
    return {
        "asset": {"version": "1.1", "generator": f"neoreef {__version__}"},
        "geometricError": max(dx, dy, dz) * 2.0,
        "root": {
            "boundingVolume": {"box": [cx, cy, cz, dx, 0, 0, 0, dy, 0, 0, 0, dz]},
            "geometricError": 0,
            "content": {"uri": glb_filename},
            "refine": "REPLACE",
        },
    }


def write_survey_meta(model_dir: Path, survey_name: str, bbox: BBox, glb_filename: str,
                      crs: Optional[str]) -> Path:
    meta = {
        "schema_version": 1,
        "survey_name": survey_name,
        "generator": f"neoreef {__version__}",
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "glb": glb_filename,
        "crs": crs,                      # None => local frame, transform required downstream
        "units": "m",
        "bbox_local": bbox,
    }
    p = model_dir / SURVEY_META_FILENAME
    with open(p, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    return p


def export_3d_model(chunk, survey_name: str, model_dir: Path, cfg: MetashapeConfig,
                    log: Log) -> Optional[Path]:
    """Run the four-step export. Returns the tileset.json path, or None on failure."""
    import Metashape
    model_dir = Path(model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)
    obj_path = model_dir / f"{survey_name}.obj"
    raw_glb = model_dir / f"{survey_name}.glb"
    final_glb = model_dir / model_glb_filename(survey_name)
    tileset_path = model_dir / TILESET_FILENAME

    log("    [1/4] Exporting OBJ from Metashape...")
    try:
        chunk.exportModel(str(obj_path), format=Metashape.ModelFormatOBJ, save_texture=True, save_normals=True)
        log(f"    [OK] OBJ exported: {obj_path}")
    except Exception as e:
        log(f"    ERROR: OBJ export failed ({e})")
        return None

    log("    [2/4] Converting OBJ -> glb (obj2gltf)...")
    if not run_tool([cfg.obj2gltf_cmd, "-i", str(obj_path), "-o", str(raw_glb), "--binary"],
                    log, "obj2gltf", cfg.tool_timeout_s):
        return None

    log("    [3/4] Compressing glb (gltfpack)...")
    if not run_tool([cfg.gltfpack_cmd, "-i", str(raw_glb), "-o", str(final_glb), *cfg.gltfpack_args],
                    log, "gltfpack", cfg.tool_timeout_s):
        log("    WARNING: gltfpack failed - using uncompressed glb")
        final_glb = raw_glb

    log("    [4/4] Generating tileset.json + survey_meta.json...")
    try:
        bbox = compute_model_bbox(chunk)
        with open(tileset_path, "w", encoding="utf-8") as f:
            json.dump(make_tileset(final_glb.name, bbox), f, indent=2)
        write_survey_meta(model_dir, survey_name, bbox, final_glb.name, cfg.set_crs)
        log(f"    [OK] tileset.json written: {tileset_path}")
    except Exception as e:
        log(f"    WARNING: tileset.json generation failed ({e})")
        return None

    for p in (obj_path, obj_path.with_suffix(".mtl")):   # textures are kept for debugging
        safe_unlink(p)
    if final_glb != raw_glb:
        safe_unlink(raw_glb)
    return tileset_path
