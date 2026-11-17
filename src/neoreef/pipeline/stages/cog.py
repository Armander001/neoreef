"""Stage ``cog``: find orthomosaics, convert to COG, extract bbox, render preview."""

from __future__ import annotations

from pathlib import Path
from typing import List

from neoreef.common.naming import compile_survey_pattern, parse_ortho_filename
from ..context import PipelineContext
from ..geo.raster import convert_to_cog, read_bbox_wgs84, render_preview_png
from ..records import OrthoRecord, RecordSet, carry_over

ORTHO_GLOB = "*_ortho.tif"


def scan_orthomosaics(ctx: PipelineContext) -> List[OrthoRecord]:
    """All ``*_ortho.tif`` under OUTPUT_BASE whose survey name matches, plus EXTRA_ORTHOS."""
    cfg, log = ctx.cfg, ctx.log
    pattern = compile_survey_pattern(cfg.survey_pattern)
    records: List[OrthoRecord] = []
    seen = set()

    if cfg.output_base.exists():
        for tif in sorted(cfg.output_base.rglob(ORTHO_GLOB)):
            parsed = parse_ortho_filename(tif.name)
            if not parsed:
                continue
            name, otype = parsed
            if not pattern.match(name):
                log.debug(f"  Skip (name mismatch): {tif.name}")
                continue
            if (name, otype) in seen:
                log.debug(f"  Skip (duplicate): {tif}")
                continue
            records.append(OrthoRecord(survey_name=name, ortho_type=otype, src_path=tif))
            seen.add((name, otype))
    else:
        log.warning(f"OUTPUT_BASE does not exist: {cfg.output_base}")

    for entry in cfg.extra_orthos:
        p = Path(entry["path"])
        name = entry.get("survey_name", p.stem)
        otype = entry.get("ortho_type", "drone")
        if (name, otype) in seen:
            continue
        if not p.exists():
            log.warning(f"  EXTRA_ORTHO not found: {p}")
            continue
        records.append(OrthoRecord(survey_name=name, ortho_type=otype, src_path=p))
        seen.add((name, otype))
        log.info(f"  Added extra ortho: {name} ({otype})")

    log.info(f"Found {len(records)} orthomosaic(s): "
             f"{sum(r.ortho_type == 'drone' for r in records)} drone, "
             f"{sum(r.ortho_type == 'coral' for r in records)} coral")
    return records


def _adopt_legacy_cog(rec: OrthoRecord, records: List[OrthoRecord], cog_dir: Path, log) -> None:
    """Rename a pre-refactor ``{survey}_cog.tif`` to the type-encoded name."""
    legacy = cog_dir / f"{rec.survey_name}_cog.tif"
    if not legacy.exists():
        return
    same_survey = [r for r in records if r.survey_name == rec.survey_name]
    if len(same_survey) != 1:
        log.warning(f"  Legacy COG {legacy.name} is ambiguous (survey has {len(same_survey)} orthos); "
                    f"delete it or rename it to {rec.cog_filename}")
        return
    legacy.rename(cog_dir / rec.cog_filename)
    log.info(f"  Renamed legacy COG {legacy.name} -> {rec.cog_filename}")


def run(ctx: PipelineContext, rs: RecordSet) -> RecordSet:
    log = ctx.log
    log.info("--- Stage: scan + COG conversion ---")
    records = scan_orthomosaics(ctx)
    carry_over(rs.orthos, records, ("ion_asset_id",))

    ctx.cog_dir.mkdir(parents=True, exist_ok=True)
    ok_n = fail_n = skip_n = 0
    for rec in records:
        dst = ctx.cog_dir / rec.cog_filename
        if not dst.exists():
            _adopt_legacy_cog(rec, records, ctx.cog_dir, log)

        if dst.exists():
            log.info(f"  [SKIP] COG already exists: {dst.name}")
            skip_n += 1
        else:
            try:
                converted = convert_to_cog(rec.src_path, dst, log)
            except Exception as e:
                log.error(f"  Unhandled error for {rec.id}: {e}")
                converted = False
            if not converted:
                fail_n += 1
                if not ctx.continue_on_error:
                    break
                continue
            ok_n += 1

        rec.cog_path = dst
        rec.bbox_wgs84 = read_bbox_wgs84(dst)
        if rec.bbox_wgs84 is None:
            log.warning(f"  {rec.id}: no CRS in the GeoTIFF; viewers cannot place it "
                        f"(upload to ion or add a georeferenced export)")
            continue

        preview = ctx.preview_dir / f"{rec.survey_name}_{rec.ortho_type}.png"
        if preview.exists() or render_preview_png(dst, preview, log=log):
            rec.preview_path = preview

    log.info(f"  COG results: ok:{ok_n}  fail:{fail_n}  skip:{skip_n}")
    rs.orthos = records
    rs.mark("cog")
    return rs
