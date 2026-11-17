"""One function per Metashape workflow step, so the batch loop reads as a recipe.

Every function takes the chunk (or document) plus the config and a ``log``
callable. ``Metashape`` is imported inside each function so the module can
be imported, and the loop unit-tested, with a stand-in module.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, List

from .config import MetashapeConfig, enum

Log = Callable[[str], None]


def open_or_create_project(psx_path: Path, log: Log):
    import Metashape
    doc = Metashape.Document()
    if os.path.exists(str(psx_path)):
        log(f"  Opening existing project: {psx_path}")
        doc.open(str(psx_path))
    else:
        log(f"  Creating new project: {psx_path}")
        doc.save(str(psx_path))
    return doc


def get_chunk(doc, label: str):
    chunk = doc.chunk if doc.chunk is not None else doc.addChunk()
    chunk.label = label
    return chunk


def apply_crs(chunk, cfg: MetashapeConfig, log: Log) -> None:
    if not cfg.set_crs:
        return
    import Metashape
    try:
        chunk.crs = Metashape.CoordinateSystem(cfg.set_crs)
        log(f"  CRS assigned: {cfg.set_crs}")
    except Exception as e:
        log(f"  WARNING: CRS assignment failed ({e}) - continuing without CRS")


def add_photos(chunk, image_paths: List[str], log: Log) -> None:
    if chunk.cameras:
        log(f"  Photos already loaded ({len(chunk.cameras)} cameras) - skipping addPhotos().")
        return
    log(f"  Adding {len(image_paths)} photos...")
    chunk.addPhotos(image_paths)
    log(f"  Photos added: {len(chunk.cameras)} cameras")


def align_photos(chunk, cfg: MetashapeConfig, log: Log) -> None:
    log(f"  [ALIGNMENT] Matching (downscale={cfg.match_downscale})...")
    chunk.matchPhotos(
        downscale=cfg.match_downscale,
        generic_preselection=cfg.generic_preselection,
        reference_preselection=cfg.reference_preselection,
        mask_tiepoints=cfg.mask_tiepoints,
        filter_stationary_points=cfg.filter_stationary,
        keypoint_limit=cfg.keypoint_limit,
        tiepoint_limit=cfg.tiepoint_limit,
    )
    log("    [OK] Matching done")
    log("  [ALIGNMENT] Aligning cameras...")
    chunk.alignCameras()
    log(f"    [OK] Aligned ({len(chunk.cameras)} cameras)")
    log("  [ALIGNMENT] Optimizing cameras...")
    try:
        chunk.optimizeCameras()
        log("    [OK] Optimization done")
    except Exception as e:
        log(f"    WARNING: optimizeCameras() skipped ({e})")


def build_depth_maps(chunk, cfg: MetashapeConfig, log: Log) -> None:
    import Metashape
    log(f"  [DEPTH MAPS] Building (downscale={cfg.depth_downscale})...")
    chunk.buildDepthMaps(downscale=cfg.depth_downscale, filter_mode=enum(Metashape, cfg.depth_filter))
    log("    [OK] Depth maps done")


def build_mesh(chunk, cfg: MetashapeConfig, log: Log) -> None:
    import Metashape
    log("  [MESH] Building from depth maps...")
    chunk.buildModel(
        source_data=Metashape.DepthMapsData,
        surface_type=enum(Metashape, cfg.mesh_surface_type),
        interpolation=enum(Metashape, cfg.ortho_interpolation),
    )
    log("    [OK] Mesh done")


def build_orthomosaic(chunk, cfg: MetashapeConfig, log: Log) -> None:
    import Metashape
    log("  [ORTHOMOSAIC] Building (local coordinate space, no GPS required)...")
    chunk.buildOrthomosaic(
        surface=Metashape.ModelData,
        blending_mode=enum(Metashape, cfg.ortho_blending),
        refine_seamlines=cfg.ortho_refine_seamlines,
        fill_holes=cfg.ortho_fill_holes,
    )
    log("    [OK] Orthomosaic done")


def export_orthomosaic_tiff(chunk, tif_path: Path, cfg: MetashapeConfig, log: Log) -> None:
    """GeoTIFF export. No world file: underwater surveys have nothing to georeference with."""
    import Metashape
    log(f"  [EXPORT] TIF -> {tif_path}")
    chunk.exportOrthomosaic(
        str(tif_path),
        image_format=Metashape.ImageFormatTIFF,
        tiff_big=cfg.ortho_bigtiff,
        write_kml=False,
        world_file=False,
    )
    log("    [OK] TIF saved")
