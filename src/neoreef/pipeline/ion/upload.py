"""Upload one file to Cesium ion, reusing a healthy existing asset by name.

Fixes the legacy behaviour where any asset with a matching name was reused
regardless of status, so a failed tiling job poisoned every later run.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from .client import COMPLETE, TERMINAL_ERROR_STATUSES, IonClient


@dataclass(frozen=True)
class IonUploadSpec:
    name: str
    asset_type: str      # "IMAGERY" | "GEOSPATIAL" | "3DTILES" ...
    source_type: str     # "GEOTIFF" | "GEOJSON" | ...
    description: str = ""


def _resolve_existing(client: IonClient, names: Iterable[str], log: logging.Logger,
                      poll_timeout: int) -> Optional[int]:
    """Return a reusable asset id, deleting broken ones along the way."""
    for name in names:
        item = client.find_by_name(name)
        if not item:
            continue
        asset_id, status = item["id"], item.get("status", "")
        if status == COMPLETE:
            log.info(f"  [ion] Reusing complete asset {asset_id}: {name}")
            return asset_id
        if status in TERMINAL_ERROR_STATUSES:
            log.warning(f"  [ion] Existing asset {asset_id} ({name}) is {status}; deleting and re-uploading")
            client.delete_asset(asset_id)
            continue
        log.info(f"  [ion] Existing asset {asset_id} ({name}) is {status or 'pending'}; waiting")
        if client.poll_ready(asset_id, timeout=poll_timeout, log=log):
            return asset_id
        log.warning(f"  [ion] Asset {asset_id} did not complete; deleting and re-uploading")
        client.delete_asset(asset_id)
    return None


def upload_file(client: IonClient, file_path: Path, spec: IonUploadSpec,
                log: logging.Logger, poll_timeout: int = 600,
                legacy_names: Iterable[str] = ()) -> Optional[int]:
    """Full upload flow. Returns the asset id, or None on failure."""
    existing = _resolve_existing(client, [spec.name, *legacy_names], log, poll_timeout)
    if existing is not None:
        return existing

    log.info(f"  [ion] Creating {spec.asset_type}/{spec.source_type} asset: {spec.name}")
    resp = client.create_asset(spec.name, spec.asset_type, spec.source_type, spec.description)
    asset_id = resp["assetMetadata"]["id"]
    log.info(f"  [ion] Asset ID: {asset_id}")

    if not client.upload_s3(resp["uploadLocation"], file_path, log):
        return None
    client.notify_complete(resp["onComplete"])

    log.info("  [ion] Polling tiling status...")
    if client.poll_ready(asset_id, timeout=poll_timeout, log=log):
        log.info(f"  [ion] Ready: asset {asset_id}")
        return asset_id
    return None
