"""Raster helpers: GeoTIFF -> COG, WGS84 bbox, PNG preview."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Tuple

BBox = Tuple[float, float, float, float]  # W, S, E, N

COG_PROFILE = {
    "driver": "GTiff",
    "compress": "DEFLATE",
    "predictor": 2,
    "tiled": True,
    "blockxsize": 512,
    "blockysize": 512,
    "BIGTIFF": "IF_SAFER",
}
OVERVIEW_LEVELS = [2, 4, 8, 16, 32, 64]


def read_bbox_wgs84(path: Path) -> Optional[BBox]:
    """WGS84 bounding box of a georeferenced raster, or None if it has no CRS."""
    try:
        import rasterio
        from rasterio.crs import CRS
        from rasterio.warp import transform_bounds
    except ImportError:
        return None
    try:
        with rasterio.open(str(path)) as ds:
            if ds.crs is None:
                return None
            b = ds.bounds
            w, s, e, n = transform_bounds(ds.crs, CRS.from_epsg(4326), b.left, b.bottom, b.right, b.top)
            return (round(w, 6), round(s, 6), round(e, 6), round(n, 6))
    except Exception:
        return None


def convert_to_cog(src_path: Path, dst_path: Path, log: logging.Logger) -> bool:
    """Convert a GeoTIFF to a Cloud Optimized GeoTIFF via windowed reads.

    Streams block by block so multi-GB inputs never load fully in memory.
    """
    try:
        import rasterio
        from rasterio.enums import Resampling
        from rasterio.shutil import copy as rio_copy
    except ImportError:
        log.error("rasterio is not installed. Run: conda install -c conda-forge rasterio")
        return False

    dst_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = dst_path.with_suffix(".tmp.tif")
    try:
        with rasterio.open(str(src_path)) as src:
            profile = src.profile.copy()
            profile.update(COG_PROFILE)
            log.info(f"  Converting to tiled GeoTIFF: {src_path.name}")
            with rasterio.open(str(tmp_path), "w", **profile) as dst:
                for _, window in src.block_windows(1):
                    dst.write(src.read(window=window), window=window)
                log.info("  Building overviews...")
                dst.build_overviews(OVERVIEW_LEVELS, Resampling.average)
                dst.update_tags(ns="rio_overview", resampling="average")

        log.info(f"  Writing COG: {dst_path.name}")
        rio_copy(str(tmp_path), str(dst_path), copy_src_overviews=True, **COG_PROFILE)
        tmp_path.unlink(missing_ok=True)
        log.info(f"  COG written: {dst_path}")
        return True
    except Exception as e:
        log.error(f"  COG conversion failed for {src_path.name}: {e}")
        tmp_path.unlink(missing_ok=True)
        return False


def render_preview_png(src_path: Path, dst_path: Path, max_px: int = 2048,
                       log: Optional[logging.Logger] = None) -> bool:
    """Write a downsampled RGBA PNG of a georeferenced raster.

    Browsers cannot decode GeoTIFFs, so this PNG (plus the bbox) is what the
    viewers drape on the globe when a layer is not hosted on Cesium ion.
    Returns False (without raising) when the source has no CRS or rasterio
    is unavailable.
    """
    try:
        import numpy as np
        import rasterio
        from rasterio.enums import Resampling
    except ImportError:
        if log:
            log.error("rasterio/numpy not installed; cannot render previews")
        return False

    try:
        with rasterio.open(str(src_path)) as ds:
            if ds.crs is None:
                return False
            scale = max(1.0, max(ds.width, ds.height) / float(max_px))
            w = max(1, int(round(ds.width / scale)))
            h = max(1, int(round(ds.height / scale)))
            bands = [1, 2, 3] if ds.count >= 3 else [1]
            data = ds.read(bands, out_shape=(len(bands), h, w), resampling=Resampling.average)
            if ds.count in (2, 4):
                alpha = ds.read(ds.count, out_shape=(h, w), resampling=Resampling.nearest)
            else:
                alpha = ds.read_masks(1, out_shape=(h, w))

        if data.dtype != np.uint8:
            out = np.empty_like(data, dtype=np.uint8)
            for i in range(data.shape[0]):
                band = data[i].astype("float64")
                valid = band[alpha > 0] if (alpha > 0).any() else band
                lo, hi = (np.percentile(valid, 2), np.percentile(valid, 98)) if valid.size else (0, 1)
                if hi <= lo:
                    hi = lo + 1
                out[i] = np.clip((band - lo) / (hi - lo) * 255.0, 0, 255).astype(np.uint8)
            data = out
        if data.shape[0] == 1:
            data = np.repeat(data, 3, axis=0)
        alpha = (alpha > 0).astype(np.uint8) * 255 if alpha.dtype != np.uint8 or alpha.max() <= 1 else alpha
        rgba = np.concatenate([data, alpha[None, ...]], axis=0)

        dst_path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(str(dst_path), "w", driver="PNG", width=w, height=h,
                           count=4, dtype="uint8") as dst:
            dst.write(rgba)
        if log:
            log.info(f"  Preview written: {dst_path.name} ({w}x{h})")
        return True
    except Exception as e:
        if log:
            log.warning(f"  Preview render failed for {src_path.name}: {e}")
        return False
