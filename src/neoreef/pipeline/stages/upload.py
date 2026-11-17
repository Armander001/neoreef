"""Stage ``upload``: push COGs and GeoJSON to Cesium ion (write token only)."""

from __future__ import annotations

from ..context import PipelineContext
from ..ion.client import IonClient
from ..ion.upload import IonUploadSpec, upload_file
from ..records import LanduseRecord, OrthoRecord, RecordSet


def ortho_spec(rec: OrthoRecord) -> IonUploadSpec:
    return IonUploadSpec(
        name=f"{rec.survey_name} [{rec.ortho_type}]",
        asset_type="IMAGERY",
        source_type="GEOTIFF",
        description=f"NeoReef {rec.ortho_type} orthomosaic - {rec.survey_name}",
    )


def landuse_spec(rec: LanduseRecord) -> IonUploadSpec:
    return IonUploadSpec(
        name=f"NeoReef Land Use {rec.year_label} {rec.calendar_year}",
        asset_type="GEOSPATIAL",
        source_type="GEOJSON",
        description=f"Ishigaki land use - {rec.year_label} / {rec.calendar_year}",
    )


def run(ctx: PipelineContext, rs: RecordSet) -> RecordSet:
    cfg, log = ctx.cfg, ctx.log
    if not cfg.use_ion:
        log.info("--- Stage: upload skipped (USE_ION=false) ---")
        return rs
    if not cfg.has_write_token:
        log.warning("CESIUM_ION_WRITE_TOKEN is not set. Skipping upload stage.")
        return rs

    log.info("--- Stage: Cesium ion upload ---")
    client = IonClient(cfg.ion_write_token)
    ok = failed = 0

    def _attempt(rec, path, spec, legacy_names=()):
        nonlocal ok, failed
        if rec.ion_asset_id is not None:
            log.info(f"  [SKIP] already has ion asset id: {rec.id}")
            ok += 1
            return True
        if path is None or not path.exists():
            log.warning(f"  No file to upload for {rec.id}, skipping")
            return True
        try:
            asset_id = upload_file(client, path, spec, log, legacy_names=legacy_names)
        except Exception as e:
            log.error(f"  ion upload failed for {rec.id}: {e}")
            asset_id = None
        if asset_id is None:
            failed += 1
            return False
        rec.ion_asset_id = asset_id
        ok += 1
        return True

    for rec in rs.orthos:
        if not _attempt(rec, rec.cog_path, ortho_spec(rec), legacy_names=(rec.survey_name,)):
            if not ctx.continue_on_error:
                break
    else:
        for rec in rs.landuse:
            if not _attempt(rec, rec.geojson_path, landuse_spec(rec)) and not ctx.continue_on_error:
                break

    log.info(f"  ion results: ok:{ok}  fail:{failed}")
    rs.mark("upload")
    return rs
