"""Stage ``landuse``: Land-useMap_* shapefiles -> WGS84 GeoJSON."""

from __future__ import annotations

from typing import List

from neoreef.common.landuse_codes import era_to_calendar
from neoreef.common.naming import (
    LANDUSE_DIR_PREFIX,
    landuse_geojson_filename,
    landuse_year_label,
)
from ..context import PipelineContext
from ..geo.vector import shp_to_geojson
from ..records import LanduseRecord, RecordSet, carry_over


def scan_landuse(ctx: PipelineContext) -> List[LanduseRecord]:
    cfg, log = ctx.cfg, ctx.log
    records: List[LanduseRecord] = []
    if not cfg.landuse_dir.exists():
        log.warning(f"LANDUSE_DIR does not exist: {cfg.landuse_dir}")
        return records

    for subdir in sorted(cfg.landuse_dir.glob(LANDUSE_DIR_PREFIX + "*")):
        if not subdir.is_dir():
            continue
        label = landuse_year_label(subdir.name)
        if not label:
            continue
        year = era_to_calendar(label)
        if year is None:
            log.warning(f"  Cannot interpret year label {label!r} in {subdir.name}; using 0")
            year = 0
        shps = sorted(subdir.glob("*.shp"))
        if not shps:
            log.warning(f"  No .shp found in {subdir.name}, skipping")
            continue
        for shp in shps:
            records.append(LanduseRecord(year_label=label, calendar_year=year,
                                         shp_path=shp, applied_crs=cfg.shapefile_fallback_crs))
    return records


def run(ctx: PipelineContext, rs: RecordSet) -> RecordSet:
    log = ctx.log
    log.info("--- Stage: land use -> GeoJSON ---")
    records = scan_landuse(ctx)
    carry_over(rs.landuse, records, ("ion_asset_id", "feature_count"))
    ctx.landuse_out_dir.mkdir(parents=True, exist_ok=True)

    for rec in records:
        out = ctx.landuse_out_dir / landuse_geojson_filename(rec.id)
        legacy = ctx.landuse_out_dir / landuse_geojson_filename(rec.legacy_id)
        if not out.exists() and legacy.exists():
            if sum(r.year_label == rec.year_label for r in records) == 1:
                legacy.rename(out)
                log.info(f"  Renamed legacy GeoJSON {legacy.name} -> {out.name}")

        if out.exists():
            log.info(f"  [SKIP] GeoJSON already exists: {out.name}")
            rec.geojson_path = out
            continue
        try:
            count = shp_to_geojson(rec.shp_path, out, ctx.cfg.shapefile_fallback_crs, log)
        except Exception as e:
            log.error(f"  Unhandled error for {rec.shp_path.name}: {e}")
            count = 0
        if count > 0:
            rec.geojson_path = out
            rec.feature_count = count
        else:
            log.error(f"  Failed to convert {rec.shp_path.name}")
            if not ctx.continue_on_error:
                break

    done = [r for r in records if r.geojson_path]
    log.info(f"Processed {len(done)} land use layer(s)")
    rs.landuse = done
    rs.mark("landuse")
    return rs
