# -*- coding: utf-8 -*-
"""
NeoReef Cesium Pipeline
=======================
Converts Metashape orthomosaic outputs and Japanese land use shapefiles into
Cesium-ready layers. Supports both Cesium ion cloud upload and local serving.

Stages:
  all      - run cog + landuse + upload (or serve) + manifest
  cog      - convert GeoTIFFs to Cloud Optimized GeoTIFF
  landuse  - convert shapefiles to GeoJSON (WGS84, TOCHICD color-coded)
  upload   - upload COGs and GeoJSON to Cesium ion
  serve    - start local HTTP server (alternative to ion upload)
  manifest - write manifest.json for the viewer

Usage:
  python cesium_pipeline.py --config cesium_config.json --stage all
  python cesium_pipeline.py --config cesium_config.json --stage landuse
  python cesium_pipeline.py --config cesium_config.json --stage serve --port 8765
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import List, Optional, Tuple

# ---------------------------------------------------------------------------
# TOCHICD color map  (国土数値情報 H23 土地利用)
# ---------------------------------------------------------------------------
TOCHICD_MAP = {
    0:  {"name_ja": "田",              "name_en": "Paddy field",          "color": "#B5E853"},
    1:  {"name_ja": "その他の農用地",    "name_en": "Other agricultural",   "color": "#FFFF99"},
    2:  {"name_ja": "森林",             "name_en": "Forest",               "color": "#228B22"},
    3:  {"name_ja": "荒地",             "name_en": "Wasteland",            "color": "#C2B280"},
    4:  {"name_ja": "建物用地",          "name_en": "Building land",        "color": "#FF6347"},
    5:  {"name_ja": "道路",             "name_en": "Road",                 "color": "#808080"},
    6:  {"name_ja": "鉄道",             "name_en": "Railway",              "color": "#A0522D"},
    7:  {"name_ja": "その他の用地",      "name_en": "Other developed",      "color": "#FFD700"},
    8:  {"name_ja": "河川地及び湖沼",    "name_en": "Rivers/lakes",         "color": "#4169E1"},
    9:  {"name_ja": "海浜",             "name_en": "Beach/coastal",        "color": "#F5DEB3"},
    10: {"name_ja": "海水域",           "name_en": "Sea/ocean",            "color": "#1E90FF"},
    11: {"name_ja": "ゴルフ場",         "name_en": "Golf course",          "color": "#90EE90"},
    12: {"name_ja": "公園・緑地",        "name_en": "Park/green space",     "color": "#7CFC00"},
    13: {"name_ja": "運動場",           "name_en": "Sports ground",        "color": "#ADFF2F"},
    14: {"name_ja": "工場・倉庫用地",    "name_en": "Industrial/warehouse", "color": "#CD853F"},
    15: {"name_ja": "公共施設用地",      "name_en": "Public facilities",    "color": "#DDA0DD"},
    16: {"name_ja": "学校用地",         "name_en": "School land",          "color": "#FFB6C1"},
    17: {"name_ja": "空地・その他",      "name_en": "Vacant/other",         "color": "#D3D3D3"},
    21: {"name_ja": "特殊地",           "name_en": "Special zone",         "color": "#9370DB"},
}
TOCHICD_DEFAULT = {"name_ja": "不明", "name_en": "Unknown", "color": "#CCCCCC"}

# Japanese era → Gregorian calendar offset
ERA_OFFSETS = {"M": 1867, "T": 1911, "S": 1925, "H": 1988, "R": 2018}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------
@dataclass
class OrthoRecord:
    survey_name: str
    ortho_type: str           # "drone" | "coral"
    src_path: Path
    cog_path: Optional[Path] = None
    ion_asset_id: Optional[int] = None
    bbox_wgs84: Optional[Tuple[float, float, float, float]] = None  # W,S,E,N

    def to_dict(self):
        d = asdict(self)
        d["src_path"] = str(self.src_path)
        d["cog_path"] = str(self.cog_path) if self.cog_path else None
        return d


@dataclass
class LanduseRecord:
    year_label: str           # e.g. "H23"
    calendar_year: int        # e.g. 2011
    shp_path: Path
    geojson_path: Optional[Path] = None
    ion_asset_id: Optional[int] = None
    feature_count: int = 0
    applied_crs: str = ""

    def to_dict(self):
        d = asdict(self)
        d["shp_path"] = str(self.shp_path)
        d["geojson_path"] = str(self.geojson_path) if self.geojson_path else None
        return d


# ---------------------------------------------------------------------------
# Logging  (mirrors NeoReef_batch.py pattern)
# ---------------------------------------------------------------------------
def make_logger(log_path: Path):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("cesium_pipeline")
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        fh = logging.FileHandler(str(log_path), encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.INFO)
        fmt = logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s",
                                datefmt="%Y-%m-%d %H:%M:%S")
        fh.setFormatter(fmt)
        ch.setFormatter(fmt)
        logger.addHandler(fh)
        logger.addHandler(ch)
    return logger


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------
def load_config(config_path: str) -> dict:
    with open(config_path, encoding="utf-8") as f:
        cfg = json.load(f)
    # Strip comment keys
    cfg = {k: v for k, v in cfg.items() if not k.startswith("_")}

    # Ensure required keys with defaults
    cfg.setdefault("SURVEY_PATTERN", r"^Ishi(?:\d{2})_S\d{3}_\d{4}_A\d$")
    cfg.setdefault("SHAPEFILE_FALLBACK_CRS", "EPSG:6685")
    cfg.setdefault("CONTINUE_ON_ERROR", True)
    cfg.setdefault("USE_ION", True)
    cfg.setdefault("LOCAL_SERVER_PORT", 8765)
    return cfg


# ---------------------------------------------------------------------------
# Stage 1 — scan_orthomosaics
# ---------------------------------------------------------------------------
def scan_orthomosaics(output_base: str, survey_pattern: str, log,
                      extra_orthos: list = None) -> List[OrthoRecord]:
    base = Path(output_base)
    if not base.exists():
        log.warning(f"OUTPUT_BASE does not exist: {base}")
        return []

    pattern = re.compile(survey_pattern)
    seen_names: set = set()
    records: List[OrthoRecord] = []

    # Coral mosaics first (more specific suffix), then drone
    for tif in sorted(base.rglob("*_coral_ortho.tif")):
        survey_name = tif.name.replace("_coral_ortho.tif", "")
        if not pattern.match(survey_name):
            log.debug(f"  Skip (name mismatch): {tif.name}")
            continue
        records.append(OrthoRecord(survey_name=survey_name, ortho_type="coral", src_path=tif))
        seen_names.add(survey_name)

    for tif in sorted(base.rglob("*_ortho.tif")):
        if tif.name.endswith("_coral_ortho.tif"):
            continue
        survey_name = tif.name.replace("_ortho.tif", "")
        if not pattern.match(survey_name):
            log.debug(f"  Skip (name mismatch): {tif.name}")
            continue
        if survey_name in seen_names:
            continue
        records.append(OrthoRecord(survey_name=survey_name, ortho_type="drone", src_path=tif))
        seen_names.add(survey_name)

    # Explicit extras from config (files with non-standard names)
    for entry in (extra_orthos or []):
        p = Path(entry["path"])
        name = entry.get("survey_name", p.stem)
        if name in seen_names:
            continue
        if not p.exists():
            log.warning(f"  EXTRA_ORTHO not found: {p}")
            continue
        records.append(OrthoRecord(
            survey_name=name,
            ortho_type=entry.get("ortho_type", "drone"),
            src_path=p,
        ))
        seen_names.add(name)
        log.info(f"  Added extra ortho: {name} ({entry.get('ortho_type','drone')})")

    log.info(f"Found {len(records)} orthomosaic(s): "
             f"{sum(r.ortho_type=='drone' for r in records)} drone, "
             f"{sum(r.ortho_type=='coral' for r in records)} coral")
    return records


# ---------------------------------------------------------------------------
# Stage 2 — convert_to_cog
# ---------------------------------------------------------------------------
def _get_bbox_wgs84(dataset) -> Optional[Tuple[float, float, float, float]]:
    """Extract WGS84 bounding box from an open rasterio dataset."""
    try:
        from rasterio.crs import CRS
        from rasterio.warp import transform_bounds
        src_crs = dataset.crs
        if src_crs is None:
            return None
        bounds = dataset.bounds
        west, south, east, north = transform_bounds(
            src_crs, CRS.from_epsg(4326),
            bounds.left, bounds.bottom, bounds.right, bounds.top
        )
        return (round(west, 6), round(south, 6), round(east, 6), round(north, 6))
    except Exception:
        return None


def convert_to_cog(src_path: Path, dst_path: Path, log) -> bool:
    """Convert a GeoTIFF to Cloud Optimized GeoTIFF using rasterio.
    Streams via windowed reads to handle multi-GB files.
    Returns True on success."""
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
            profile.update({
                "driver": "GTiff",
                "compress": "DEFLATE",
                "predictor": 2,
                "tiled": True,
                "blockxsize": 512,
                "blockysize": 512,
                "BIGTIFF": "IF_SAFER",
            })

            log.info(f"  Converting to tiled GeoTIFF: {src_path.name}")
            with rasterio.open(str(tmp_path), "w", **profile) as dst:
                windows = list(src.block_windows(1))
                for _, window in windows:
                    data = src.read(window=window)
                    dst.write(data, window=window)

                log.info(f"  Building overviews...")
                overview_levels = [2, 4, 8, 16, 32, 64]
                dst.build_overviews(overview_levels, Resampling.average)
                dst.update_tags(ns="rio_overview", resampling="average")

        log.info(f"  Writing COG: {dst_path.name}")
        rio_copy(str(tmp_path), str(dst_path), copy_src_overviews=True,
                 compress="DEFLATE", predictor=2,
                 tiled=True, blockxsize=512, blockysize=512,
                 BIGTIFF="IF_SAFER")
        tmp_path.unlink(missing_ok=True)
        log.info(f"  COG written: {dst_path}")
        return True

    except Exception as e:
        log.error(f"  COG conversion failed for {src_path.name}: {e}")
        tmp_path.unlink(missing_ok=True)
        return False


def batch_convert_orthos(records: List[OrthoRecord], out_dir: Path,
                         log, continue_on_error: bool) -> dict:
    results = {"successful": [], "failed": [], "skipped": []}
    cog_dir = out_dir / "cogs"
    cog_dir.mkdir(parents=True, exist_ok=True)

    for rec in records:
        dst = cog_dir / f"{rec.survey_name}_cog.tif"
        if dst.exists():
            log.info(f"  [SKIP] COG already exists: {dst.name}")
            rec.cog_path = dst
            results["skipped"].append(rec.survey_name)
            _fill_bbox(rec, log)
            continue
        try:
            ok = convert_to_cog(rec.src_path, dst, log)
            if ok:
                rec.cog_path = dst
                _fill_bbox(rec, log)
                results["successful"].append(rec.survey_name)
            else:
                results["failed"].append(rec.survey_name)
                if not continue_on_error:
                    break
        except Exception as e:
            log.error(f"  Unhandled error for {rec.survey_name}: {e}")
            results["failed"].append(rec.survey_name)
            if not continue_on_error:
                break

    return results


def _fill_bbox(rec: OrthoRecord, log):
    if rec.cog_path and rec.cog_path.exists():
        try:
            import rasterio
            with rasterio.open(str(rec.cog_path)) as ds:
                rec.bbox_wgs84 = _get_bbox_wgs84(ds)
        except Exception as e:
            log.warning(f"  Could not extract bbox for {rec.survey_name}: {e}")


# ---------------------------------------------------------------------------
# Stage 3 — process_landuse
# ---------------------------------------------------------------------------
def _era_to_calendar(year_label: str) -> int:
    """Convert Japanese era year label (e.g. 'H23', 'R02') to calendar year."""
    m = re.match(r"^([MTSH R])(\d+)$", year_label.strip(), re.IGNORECASE)
    if not m:
        # Fallback: try to parse as plain year
        try:
            return int(year_label)
        except ValueError:
            return 0
    era = m.group(1).upper()
    num = int(m.group(2))
    offset = ERA_OFFSETS.get(era, 0)
    return offset + num


def _detect_crs(shp_path: Path) -> Optional[str]:
    prj = shp_path.with_suffix(".prj")
    if prj.exists() and prj.stat().st_size > 10:
        try:
            import fiona
            with fiona.open(str(shp_path)) as src:
                return src.crs_wkt if hasattr(src, "crs_wkt") else str(src.crs)
        except Exception:
            return None
    return None


def shp_to_geojson(shp_path: Path, out_path: Path, fallback_crs: str, log) -> int:
    """Convert shapefile to WGS84 GeoJSON with TOCHICD color properties.
    Returns feature count, or 0 on failure."""
    try:
        import geopandas as gpd
    except ImportError:
        log.error("geopandas is not installed. Run: conda install -c conda-forge geopandas")
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)

    detected = _detect_crs(shp_path)
    if detected:
        log.info(f"  CRS from .prj: detected")
        gdf = gpd.read_file(str(shp_path))
    else:
        log.warning(f"  No .prj found — applying fallback CRS: {fallback_crs}")
        gdf = gpd.read_file(str(shp_path))
        gdf = gdf.set_crs(fallback_crs, allow_override=True)

    # Reproject to WGS84
    gdf = gdf.to_crs("EPSG:4326")

    # Add TOCHICD color properties for Cesium styling
    def get_color(row):
        code = int(row.get("TOCHICD", -1)) if row.get("TOCHICD") is not None else -1
        return TOCHICD_MAP.get(code, TOCHICD_DEFAULT)["color"]

    def get_name_en(row):
        code = int(row.get("TOCHICD", -1)) if row.get("TOCHICD") is not None else -1
        return TOCHICD_MAP.get(code, TOCHICD_DEFAULT)["name_en"]

    def get_name_ja(row):
        code = int(row.get("TOCHICD", -1)) if row.get("TOCHICD") is not None else -1
        return TOCHICD_MAP.get(code, TOCHICD_DEFAULT)["name_ja"]

    gdf["fill_color"] = gdf.apply(lambda r: get_color(r), axis=1)
    gdf["stroke_color"] = "#000000"
    gdf["fill_opacity"] = 0.6
    gdf["land_use_en"] = gdf.apply(lambda r: get_name_en(r), axis=1)
    gdf["land_use_ja"] = gdf.apply(lambda r: get_name_ja(r), axis=1)

    gdf.to_file(str(out_path), driver="GeoJSON")
    log.info(f"  GeoJSON written ({len(gdf)} features): {out_path.name}")
    return len(gdf)


def batch_process_landuse(landuse_dir: str, out_dir: Path,
                          fallback_crs: str, log,
                          continue_on_error: bool) -> List[LanduseRecord]:
    base = Path(landuse_dir)
    if not base.exists():
        log.warning(f"LANDUSE_DIR does not exist: {base}")
        return []

    records: List[LanduseRecord] = []
    # Find all Land-useMap_* subdirectories
    for subdir in sorted(base.glob("Land-useMap_*")):
        if not subdir.is_dir():
            continue
        year_label = subdir.name.replace("Land-useMap_", "")
        calendar_year = _era_to_calendar(year_label)

        # Find the shapefile inside (any .shp)
        shp_files = list(subdir.glob("*.shp"))
        if not shp_files:
            log.warning(f"  No .shp found in {subdir.name}, skipping")
            continue

        for shp_path in shp_files:
            rec = LanduseRecord(
                year_label=year_label,
                calendar_year=calendar_year,
                shp_path=shp_path,
                applied_crs=fallback_crs,
            )
            out_path = out_dir / "landuse" / f"landuse_{year_label}.geojson"

            if out_path.exists():
                log.info(f"  [SKIP] GeoJSON already exists: {out_path.name}")
                rec.geojson_path = out_path
                records.append(rec)
                continue

            try:
                count = shp_to_geojson(shp_path, out_path, fallback_crs, log)
                if count > 0:
                    rec.geojson_path = out_path
                    rec.feature_count = count
                    records.append(rec)
                else:
                    log.error(f"  Failed to convert {shp_path.name}")
                    if not continue_on_error:
                        return records
            except Exception as e:
                log.error(f"  Unhandled error for {shp_path.name}: {e}")
                if not continue_on_error:
                    return records

    log.info(f"Processed {len(records)} land use layer(s)")
    return records


# ---------------------------------------------------------------------------
# Stage 4 — ion_upload
# Per https://cesium.com/learn/ion/ion-upload-rest/ the 4-step flow is:
#   1. POST /v1/assets  → get assetMetadata, uploadLocation, onComplete
#   2. PUT file to S3 using uploadLocation credentials
#   3. POST to onComplete.url with onComplete.fields  (NOT a hardcoded endpoint)
#   4. Poll GET /v1/assets/{id} until status == COMPLETE
# ---------------------------------------------------------------------------

def _ion_list_assets(token: str, search: str = None) -> list:
    """Return list of ion asset dicts, optionally filtered by name search."""
    import requests
    headers = {"Authorization": f"Bearer {token}"}
    params = {"search": search} if search else {}
    resp = requests.get("https://api.cesium.com/v1/assets", headers=headers,
                        params=params, timeout=30)
    if resp.status_code != 200:
        return []
    return resp.json().get("items", [])


def _ion_find_asset_by_name(token: str, name: str) -> Optional[int]:
    """Return existing ion asset_id if an asset with this exact name already exists, else None."""
    for item in _ion_list_assets(token, search=name):
        if item.get("name") == name:
            return item["id"]
    return None


def _ion_create_asset(token: str, name: str, asset_type: str,
                      source_type: str, description: str = "") -> dict:
    """Step 1: Create asset metadata. Returns full response (assetMetadata + uploadLocation + onComplete)."""
    import requests
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = {
        "name": name,
        "description": description,
        "type": asset_type,
        "options": {"sourceType": source_type},
    }
    resp = requests.post("https://api.cesium.com/v1/assets", json=body,
                         headers=headers, timeout=30)
    if not resp.ok:
        raise requests.HTTPError(
            f"{resp.status_code} {resp.reason} — body: {resp.text[:400]}",
            response=resp
        )
    return resp.json()


def _ion_upload_s3(upload_location: dict, file_path: Path, log) -> bool:
    """Step 2: Upload file to the S3 bucket using temporary credentials from uploadLocation."""
    try:
        import boto3
    except ImportError:
        log.error("boto3 is required for ion upload. Install: pip install boto3")
        return False

    try:
        s3 = boto3.client(
            "s3",
            aws_access_key_id=upload_location["accessKey"],
            aws_secret_access_key=upload_location["secretAccessKey"],
            aws_session_token=upload_location["sessionToken"],
            region_name="us-east-1",
        )
        bucket = upload_location["bucket"]
        prefix = upload_location.get("prefix", "")
        key = prefix + file_path.name

        file_size_mb = file_path.stat().st_size / (1024 * 1024)
        log.info(f"  S3 upload: {file_path.name} ({file_size_mb:.0f} MB) → s3://{bucket}/{key}")

        # Use multipart for large files (> 100 MB)
        config = boto3.s3.transfer.TransferConfig(
            multipart_threshold=100 * 1024 * 1024,
            multipart_chunksize=50 * 1024 * 1024,
            max_concurrency=4,
        )
        s3.upload_file(
            str(file_path), bucket, key,
            ExtraArgs={"ContentType": "application/octet-stream"},
            Config=config,
        )
        log.info(f"  S3 upload complete")
        return True
    except Exception as e:
        log.error(f"  S3 upload failed: {e}")
        return False


def _ion_notify_complete(token: str, on_complete: dict, log) -> None:
    """Step 3: POST to onComplete.url with onComplete.fields to trigger ion tiling."""
    import requests
    url    = on_complete["url"]
    method = on_complete.get("method", "POST").upper()
    fields = on_complete.get("fields", {})
    headers = {"Authorization": f"Bearer {token}"}
    log.info(f"  Notifying ion tiling engine: {method} {url}")
    if method == "POST":
        resp = requests.post(url, json=fields, headers=headers, timeout=30)
    else:
        resp = requests.request(method, url, json=fields, headers=headers, timeout=30)
    # ion returns 204 No Content on success
    if resp.status_code not in (200, 204):
        log.warning(f"  onComplete returned HTTP {resp.status_code}: {resp.text[:200]}")
    resp.raise_for_status()


def _ion_poll_ready(token: str, asset_id: int, timeout: int = 600, log=None) -> bool:
    """Step 4: Poll until status == COMPLETE (or ERROR / timeout)."""
    import requests
    headers  = {"Authorization": f"Bearer {token}"}
    url      = f"https://api.cesium.com/v1/assets/{asset_id}"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            data   = resp.json()
            status = data.get("status", "AWAITING_FILES")
            if log:
                log.info(f"  ion asset {asset_id} status: {status}")
            if status == "COMPLETE":
                return True
            if status in ("ERROR", "DATA_ERROR"):
                if log:
                    log.error(f"  ion tiling failed (status={status}): "
                              f"{data.get('errorMessage', 'no details')}")
                return False
        except Exception as e:
            if log:
                log.warning(f"  Poll error: {e}")
        time.sleep(20)
    if log:
        log.warning(f"  Timed out waiting for ion asset {asset_id}")
    return False


def _ion_upload_asset(token: str, file_path: Path,
                      name: str, asset_type: str, source_type: str,
                      description: str, log) -> Optional[int]:
    """Full 4-step ion upload. Returns asset_id on success, None on failure."""
    # Check for pre-existing asset with the same name (from a previous failed run)
    existing_id = _ion_find_asset_by_name(token, name)
    if existing_id is not None:
        log.info(f"  [ion] Asset already exists (id={existing_id}), reusing: {name}")
        return existing_id

    # Step 1 — create
    log.info(f"  [ion] Creating {asset_type}/{source_type} asset: {name}")
    resp        = _ion_create_asset(token, name, asset_type, source_type, description)
    asset_id    = resp["assetMetadata"]["id"]
    upload_loc  = resp["uploadLocation"]
    on_complete = resp["onComplete"]
    log.info(f"  [ion] Asset ID: {asset_id}")

    # Step 2 — upload to S3
    if not _ion_upload_s3(upload_loc, file_path, log):
        return None

    # Step 3 — notify completion
    _ion_notify_complete(token, on_complete, log)

    # Step 4 — poll
    log.info(f"  [ion] Polling tiling status...")
    ok = _ion_poll_ready(token, asset_id, timeout=600, log=log)
    if ok:
        log.info(f"  [ion] Ready: asset {asset_id}")
        return asset_id
    return None


def ion_upload_ortho(rec: OrthoRecord, token: str, log) -> bool:
    if rec.cog_path is None or not rec.cog_path.exists():
        log.warning(f"  No COG file for {rec.survey_name}, skipping ion upload")
        return False
    try:
        asset_id = _ion_upload_asset(
            token, rec.cog_path,
            name=rec.survey_name,
            asset_type="IMAGERY",
            source_type="GEOTIFF",
            description=f"NeoReef {rec.ortho_type} orthomosaic — {rec.survey_name}",
            log=log,
        )
        if asset_id is not None:
            rec.ion_asset_id = asset_id
            return True
        return False
    except Exception as e:
        log.error(f"  ion upload failed for {rec.survey_name}: {e}")
        return False


def ion_upload_landuse(rec: LanduseRecord, token: str, log) -> bool:
    if rec.geojson_path is None or not rec.geojson_path.exists():
        log.warning(f"  No GeoJSON for {rec.year_label}, skipping ion upload")
        return False
    try:
        asset_id = _ion_upload_asset(
            token, rec.geojson_path,
            name=f"NeoReef Land Use {rec.year_label} {rec.calendar_year}",
            asset_type="GEOSPATIAL",
            source_type="GEOJSON",
            description=f"Ishigaki land use — {rec.year_label} / {rec.calendar_year}",
            log=log,
        )
        if asset_id is not None:
            rec.ion_asset_id = asset_id
            return True
        return False
    except Exception as e:
        log.error(f"  ion upload failed for landuse_{rec.year_label}: {e}")
        return False


def batch_ion_upload(ortho_records: List[OrthoRecord],
                     landuse_records: List[LanduseRecord],
                     token: str, log,
                     continue_on_error: bool) -> dict:
    results = {"successful": [], "failed": []}
    for rec in ortho_records:
        if rec.ion_asset_id is not None:
            log.info(f"  [SKIP] already has ion asset id: {rec.survey_name}")
            results["successful"].append(rec.survey_name)
            continue
        ok = ion_upload_ortho(rec, token, log)
        (results["successful"] if ok else results["failed"]).append(rec.survey_name)
        if not ok and not continue_on_error:
            return results

    for rec in landuse_records:
        if rec.ion_asset_id is not None:
            log.info(f"  [SKIP] already has ion asset id: landuse_{rec.year_label}")
            results["successful"].append(f"landuse_{rec.year_label}")
            continue
        ok = ion_upload_landuse(rec, token, log)
        label = f"landuse_{rec.year_label}"
        (results["successful"] if ok else results["failed"]).append(label)
        if not ok and not continue_on_error:
            return results

    return results


# ---------------------------------------------------------------------------
# Stage 5 — write_manifest
# ---------------------------------------------------------------------------
def write_manifest(ortho_records: List[OrthoRecord],
                   landuse_records: List[LanduseRecord],
                   out_dir: Path,
                   ion_token: str,
                   use_ion: bool,
                   local_port: int,
                   log,
                   known_ion_assets: dict = None) -> Path:
    manifest = {
        "generated": datetime.utcnow().isoformat() + "Z",
        "cesium_ion_token": ion_token if use_ion else "",
        "use_ion": use_ion,
        "base_ion_imagery_asset": None,   # legacy imagery base (set by main if present)
        "base_ion_3dtiles_asset": None,   # 3D tileset base e.g. Google Photorealistic
        "survey_area": {
            "name": "Ishigaki Island",
            "center_lon": 124.205,
            "center_lat": 24.470,
            "default_altitude_m": 15000,
        },
        "orthomosaics": [],
        "landuse_layers": [],
    }

    base_url = f"http://localhost:{local_port}"
    known = known_ion_assets or {}

    for rec in ortho_records:
        # Apply manually-set ion asset IDs from config if pipeline hasn't uploaded yet
        asset_id = rec.ion_asset_id or known.get(rec.survey_name)
        entry = {
            "id": rec.survey_name,
            "survey_name": rec.survey_name,
            "ortho_type": rec.ortho_type,
            "bbox_wgs84": list(rec.bbox_wgs84) if rec.bbox_wgs84 else None,
            "ion_asset_id": asset_id,
            "cog_url": f"{base_url}/cogs/{rec.survey_name}_cog.tif" if rec.cog_path else None,
        }
        manifest["orthomosaics"].append(entry)

    for rec in landuse_records:
        layer_id = f"landuse_{rec.year_label}"
        # Apply pre-known ion asset ID from config if not already uploaded
        asset_id = rec.ion_asset_id or known.get(layer_id) or known.get(rec.year_label)
        entry = {
            "id": layer_id,
            "year_label": rec.year_label,
            "calendar_year": rec.calendar_year,
            "feature_count": rec.feature_count,
            "ion_asset_id": asset_id,
            "geojson_url": f"{base_url}/landuse/landuse_{rec.year_label}.geojson" if rec.geojson_path else None,
        }
        manifest["landuse_layers"].append(entry)

    out_path = out_dir / "manifest.json"
    with open(str(out_path), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    log.info(f"Manifest written: {out_path}")

    # Copy viewer HTML into the output dir so it can be served alongside manifest.json
    # Opening the HTML via file:// breaks fetch(); it must be served via HTTP.
    viewer_src = Path(__file__).parent / "cesium_viewer.html"
    viewer_dst = out_dir / "cesium_viewer.html"
    if viewer_src.exists():
        import shutil
        shutil.copy2(str(viewer_src), str(viewer_dst))
        log.info(f"Viewer copied to: {viewer_dst}")
        log.info(f"Open viewer at:   http://localhost:{local_port}/cesium_viewer.html")
        log.info(f"  (run --stage serve first to start the local server)")
    else:
        log.warning(f"cesium_viewer.html not found at {viewer_src} — copy it manually to {out_dir}")

    return out_path


# ---------------------------------------------------------------------------
# Local server (alternative to ion upload)
# ---------------------------------------------------------------------------
class _CORSHandler(SimpleHTTPRequestHandler):
    """Adds CORS headers so the CesiumJS viewer can fetch local files."""
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Range")
        self.send_header("Access-Control-Expose-Headers", "Content-Length, Content-Range")
        super().end_headers()

    def log_message(self, fmt, *args):
        pass  # Suppress request spam


def start_local_server(serve_dir: Path, port: int, log):
    os.chdir(str(serve_dir))
    server = HTTPServer(("localhost", port), _CORSHandler)
    log.info(f"Local server started at http://localhost:{port}  (serving {serve_dir})")
    log.info("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Server stopped.")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="NeoReef Cesium Pipeline — prepare geospatial data for CesiumJS"
    )
    parser.add_argument("--config", default="cesium_config.json",
                        help="Path to cesium_config.json")
    parser.add_argument("--stage", default="all",
                        choices=["all", "cog", "landuse", "upload", "serve", "manifest"],
                        help="Pipeline stage to run")
    parser.add_argument("--port", type=int, default=None,
                        help="Override LOCAL_SERVER_PORT from config")
    args = parser.parse_args()

    cfg = load_config(args.config)
    out_dir = Path(cfg["CESIUM_OUTPUT_DIR"])
    out_dir.mkdir(parents=True, exist_ok=True)

    log = make_logger(out_dir / "cesium_pipeline.log")
    log.info("=" * 60)
    log.info(f"NeoReef Cesium Pipeline  —  stage: {args.stage}")
    log.info(f"Config: {args.config}")
    log.info("=" * 60)

    cont = cfg["CONTINUE_ON_ERROR"]
    port = args.port or cfg["LOCAL_SERVER_PORT"]
    token = cfg.get("CESIUM_ION_TOKEN", "")
    use_ion = cfg.get("USE_ION", True)

    ortho_records: List[OrthoRecord] = []
    landuse_records: List[LanduseRecord] = []

    # ---- Stage: cog --------------------------------------------------------
    if args.stage in ("all", "cog"):
        log.info("--- Stage: scan + COG conversion ---")
        ortho_records = scan_orthomosaics(
            cfg["OUTPUT_BASE"], cfg["SURVEY_PATTERN"], log,
            extra_orthos=cfg.get("EXTRA_ORTHOS", [])
        )
        if ortho_records:
            results = batch_convert_orthos(ortho_records, out_dir, log, cont)
            log.info(f"  COG results — ok:{len(results['successful'])}  "
                     f"fail:{len(results['failed'])}  "
                     f"skip:{len(results['skipped'])}")

    # ---- Stage: landuse ----------------------------------------------------
    if args.stage in ("all", "landuse"):
        log.info("--- Stage: land use -> GeoJSON ---")
        landuse_records = batch_process_landuse(
            cfg["LANDUSE_DIR"], out_dir,
            cfg["SHAPEFILE_FALLBACK_CRS"], log, cont
        )

    # ---- Stage: upload ------------------------------------------------------
    if args.stage in ("all", "upload"):
        if not use_ion:
            log.info("--- Stage: upload skipped (USE_ION=false) ---")
        elif not token or token == "YOUR_ION_ACCESS_TOKEN_HERE":
            log.warning("CESIUM_ION_TOKEN is not set. Skipping upload stage.")
        else:
            log.info("--- Stage: Cesium ion upload ---")
            # Re-scan if records are empty (e.g. running upload stage standalone)
            if not ortho_records:
                ortho_records = scan_orthomosaics(
                    cfg["OUTPUT_BASE"], cfg["SURVEY_PATTERN"], log,
                    extra_orthos=cfg.get("EXTRA_ORTHOS", [])
                )
                # Reattach COG paths
                cog_dir = out_dir / "cogs"
                for r in ortho_records:
                    p = cog_dir / f"{r.survey_name}_cog.tif"
                    if p.exists():
                        r.cog_path = p
                        _fill_bbox(r, log)
            if not landuse_records:
                landuse_records = batch_process_landuse(
                    cfg["LANDUSE_DIR"], out_dir,
                    cfg["SHAPEFILE_FALLBACK_CRS"], log, cont
                )
            results = batch_ion_upload(ortho_records, landuse_records, token, log, cont)
            log.info(f"  ion results — ok:{len(results['successful'])}  "
                     f"fail:{len(results['failed'])}")

    # ---- Stage: manifest ---------------------------------------------------
    if args.stage in ("all", "manifest"):
        log.info("--- Stage: write manifest ---")
        # When running manifest standalone, rebuild records from existing files on disk
        if not ortho_records:
            cog_dir = out_dir / "cogs"
            # Build a lookup from EXTRA_ORTHOS so non-standard names get the right type
            extra_type_map = {
                e["survey_name"]: e.get("ortho_type", "drone")
                for e in cfg.get("EXTRA_ORTHOS", [])
                if "survey_name" in e
            }
            for cog in sorted(cog_dir.glob("*_cog.tif")):
                survey_name = cog.name.replace("_cog.tif", "")
                if survey_name in extra_type_map:
                    ortho_type = extra_type_map[survey_name]
                elif survey_name.endswith("_coral"):
                    ortho_type = "coral"
                else:
                    ortho_type = "drone"
                rec = OrthoRecord(survey_name=survey_name, ortho_type=ortho_type,
                                  src_path=cog, cog_path=cog)
                _fill_bbox(rec, log)
                ortho_records.append(rec)
        if not landuse_records:
            landuse_records = batch_process_landuse(
                cfg["LANDUSE_DIR"], out_dir,
                cfg["SHAPEFILE_FALLBACK_CRS"], log, cont
            )
        m_path = write_manifest(ortho_records, landuse_records, out_dir,
                                token, use_ion, port, log,
                                known_ion_assets=cfg.get("known_ion_assets", {}))
        # Inject base asset IDs into the written manifest
        with open(str(m_path), "r", encoding="utf-8") as f:
            mdata = json.load(f)
        changed = False
        if cfg.get("BASE_ION_IMAGERY_ASSET") is not None:
            mdata["base_ion_imagery_asset"] = cfg["BASE_ION_IMAGERY_ASSET"]
            log.info(f"  Base imagery asset: {cfg['BASE_ION_IMAGERY_ASSET']}")
            changed = True
        if cfg.get("BASE_ION_3DTILES_ASSET") is not None:
            mdata["base_ion_3dtiles_asset"] = cfg["BASE_ION_3DTILES_ASSET"]
            log.info(f"  Base 3D tiles asset: {cfg['BASE_ION_3DTILES_ASSET']}")
            changed = True
        if changed:
            with open(str(m_path), "w", encoding="utf-8") as f:
                json.dump(mdata, f, indent=2, ensure_ascii=False)

    # ---- Stage: serve ------------------------------------------------------
    if args.stage == "serve":
        log.info("--- Stage: local HTTP server ---")
        start_local_server(out_dir, port, log)

    log.info("Pipeline complete.")


if __name__ == "__main__":
    main()
