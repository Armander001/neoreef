"""Vector helpers: shapefile -> WGS84 GeoJSON with TOCHICD styling attributes."""

from __future__ import annotations

import logging
from pathlib import Path

from neoreef.common.landuse_codes import lookup

TOCHICD_COLUMN = "TOCHICD"
STROKE_COLOR = "#000000"
FILL_OPACITY = 0.6


def has_prj(shp_path: Path) -> bool:
    """True if the shapefile ships a usable .prj (projection) sidecar."""
    prj = shp_path.with_suffix(".prj")
    return prj.exists() and prj.stat().st_size > 10


def shp_to_geojson(shp_path: Path, out_path: Path, fallback_crs: str,
                   log: logging.Logger) -> int:
    """Reproject a shapefile to WGS84 GeoJSON and add legend attributes.

    Adds ``fill_color``, ``stroke_color``, ``fill_opacity``, ``land_use_en``,
    ``land_use_ja`` and ``extrude_h`` from the shared TOCHICD table.
    Returns the feature count, or 0 on failure.
    """
    try:
        import geopandas as gpd
    except ImportError:
        log.error("geopandas is not installed. Run: conda install -c conda-forge geopandas")
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    gdf = gpd.read_file(str(shp_path))
    if has_prj(shp_path) and gdf.crs is not None:
        log.info(f"  CRS from .prj: {gdf.crs}")
    else:
        log.warning(f"  No .prj found; applying fallback CRS: {fallback_crs}")
        gdf = gdf.set_crs(fallback_crs, allow_override=True)
    gdf = gdf.to_crs("EPSG:4326")

    codes = gdf[TOCHICD_COLUMN] if TOCHICD_COLUMN in gdf.columns else [None] * len(gdf)
    entries = [lookup(c) for c in codes]
    gdf["fill_color"] = [e["color"] for e in entries]
    gdf["stroke_color"] = STROKE_COLOR
    gdf["fill_opacity"] = FILL_OPACITY
    gdf["land_use_en"] = [e["name_en"] for e in entries]
    gdf["land_use_ja"] = [e["name_ja"] for e in entries]
    gdf["extrude_h"] = [e["extrude_h"] for e in entries]

    gdf.to_file(str(out_path), driver="GeoJSON")
    log.info(f"  GeoJSON written ({len(gdf)} features): {out_path.name}")
    return len(gdf)
