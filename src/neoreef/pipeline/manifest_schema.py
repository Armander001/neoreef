"""manifest.json: the contract between the pipeline and the browser viewers.

:func:`build_manifest` is a pure function of ``(RecordSet, PipelineConfig)``
so it can be golden-file tested. Viewers refuse a manifest whose
``schema_version`` they do not know.

Schema v2 changes vs the legacy (unversioned) manifest
------------------------------------------------------
* ``viewer_ion_token`` replaces ``cesium_ion_token``; it is the read-only token.
* ``legend_url`` points at the generated ``tochicd_legend.json``.
* ortho ``id`` is ``{survey}:{type}`` (a survey can have a drone AND a coral ortho).
* orthos carry ``preview_url`` (PNG) for the non-ion fallback; ``cog_url`` is
  informational (browsers cannot decode a GeoTIFF).
* landuse ``id`` includes the shapefile stem.
* models carry ``position`` + ``placed`` so the viewer never loads a tileset
  that would render at Earth's centre.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from neoreef.common.geodesy import SURVEY_AREA
from .config import PipelineConfig
from .context import COG_SUBDIR, LANDUSE_SUBDIR, MODELS_SUBDIR, PREVIEW_SUBDIR
from .records import RecordSet

MANIFEST_SCHEMA_VERSION = 2
MANIFEST_FILENAME = "manifest.json"
LEGEND_FILENAME = "tochicd_legend.json"


def _url(base: str, rel: str) -> str:
    return f"{base}/{rel}" if base else rel


def build_manifest(rs: RecordSet, cfg: PipelineConfig,
                   generated: Optional[datetime] = None) -> Dict[str, Any]:
    base = cfg.server_base_url.rstrip("/")
    known = cfg.known_ion_assets
    ts = (generated or datetime.now(timezone.utc)).astimezone(timezone.utc)

    manifest: Dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "generated": ts.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "viewer_ion_token": cfg.ion_viewer_token if (cfg.use_ion and cfg.has_viewer_token) else "",
        "use_ion": bool(cfg.use_ion),
        "base_ion_imagery_asset": cfg.base_ion_imagery_asset,
        "base_ion_3dtiles_asset": cfg.base_ion_3dtiles_asset,
        "legend_url": _url(base, LEGEND_FILENAME),
        "survey_area": dict(SURVEY_AREA),
        "orthomosaics": [],
        "landuse_layers": [],
        "models_3d": [],
    }

    for rec in rs.orthos:
        asset_id = rec.ion_asset_id or known.get(rec.id) or known.get(rec.survey_name)
        manifest["orthomosaics"].append({
            "id": rec.id,
            "survey_name": rec.survey_name,
            "ortho_type": rec.ortho_type,
            "bbox_wgs84": list(rec.bbox_wgs84) if rec.bbox_wgs84 else None,
            "ion_asset_id": asset_id,
            "cog_url": _url(base, f"{COG_SUBDIR}/{rec.cog_path.name}") if rec.cog_path else None,
            "preview_url": _url(base, f"{PREVIEW_SUBDIR}/{rec.preview_path.name}") if rec.preview_path else None,
        })

    for rec in rs.landuse:
        asset_id = (rec.ion_asset_id or known.get(rec.id) or known.get(rec.legacy_id)
                    or known.get(rec.year_label))
        manifest["landuse_layers"].append({
            "id": rec.id,
            "year_label": rec.year_label,
            "calendar_year": rec.calendar_year,
            "feature_count": rec.feature_count,
            "ion_asset_id": asset_id,
            "geojson_url": _url(base, f"{LANDUSE_SUBDIR}/{rec.geojson_path.name}") if rec.geojson_path else None,
        })

    for rec in rs.models:
        entry: Dict[str, Any] = {
            "id": rec.id,
            "survey_name": rec.survey_name,
            "model_type": rec.model_type,
            "format": rec.format,
            "ion_asset_id": rec.ion_asset_id,
            "position": rec.position,
            "placed": bool(rec.placed),
        }
        if rec.format == "3dtiles":
            entry["tileset_url"] = (_url(base, f"{MODELS_SUBDIR}/{rec.survey_name}/{rec.output_path.name}")
                                    if rec.output_path else None)
        else:
            entry["gltf_url"] = (_url(base, f"{MODELS_SUBDIR}/{rec.output_path.name}")
                                 if rec.output_path else None)
        manifest["models_3d"].append(entry)

    return manifest


__all__ = ["MANIFEST_SCHEMA_VERSION", "MANIFEST_FILENAME", "LEGEND_FILENAME", "build_manifest"]
