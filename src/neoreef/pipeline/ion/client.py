"""Minimal Cesium ion REST client (https://cesium.com/learn/ion/rest-api/).

Upload flow (https://cesium.com/learn/ion/ion-upload-rest/):
  1. POST /v1/assets                -> assetMetadata, uploadLocation, onComplete
  2. PUT the file to S3 with the temporary credentials in uploadLocation
  3. POST onComplete.url with onComplete.fields to start tiling
  4. GET /v1/assets/{id} until status == COMPLETE

The HTTP session is injectable so tests never touch the network.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

ION_API = "https://api.cesium.com/v1"
TERMINAL_ERROR_STATUSES = ("ERROR", "DATA_ERROR")
COMPLETE = "COMPLETE"


class IonError(RuntimeError):
    pass


class IonClient:
    def __init__(self, token: str, session=None, api_base: str = ION_API,
                 sleep: Callable[[float], None] = time.sleep, timeout: int = 30):
        if not token:
            raise IonError("an ion access token is required")
        self._token = token
        self._session = session
        self.api_base = api_base.rstrip("/")
        self._sleep = sleep
        self.timeout = timeout

    # -- plumbing ------------------------------------------------------------
    @property
    def session(self):
        if self._session is None:
            import requests
            self._session = requests.Session()
        return self._session

    def _headers(self, json_body: bool = False) -> Dict[str, str]:
        h = {"Authorization": f"Bearer {self._token}"}
        if json_body:
            h["Content-Type"] = "application/json"
        return h

    def _check(self, resp, what: str):
        if not getattr(resp, "ok", 200 <= resp.status_code < 300):
            raise IonError(f"{what}: HTTP {resp.status_code} {getattr(resp, 'reason', '')} "
                           f"- {getattr(resp, 'text', '')[:400]}")
        return resp

    # -- assets ---------------------------------------------------------------
    def list_assets(self, search: Optional[str] = None) -> List[Dict[str, Any]]:
        params = {"search": search} if search else {}
        resp = self.session.get(f"{self.api_base}/assets", headers=self._headers(),
                                params=params, timeout=self.timeout)
        if resp.status_code != 200:
            return []
        return resp.json().get("items", [])

    def find_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """The asset dict (incl. ``status``) with exactly this name, else None."""
        for item in self.list_assets(search=name):
            if item.get("name") == name:
                return item
        return None

    def get_asset(self, asset_id: int) -> Dict[str, Any]:
        resp = self.session.get(f"{self.api_base}/assets/{asset_id}", headers=self._headers(),
                                timeout=self.timeout)
        self._check(resp, f"get asset {asset_id}")
        return resp.json()

    def delete_asset(self, asset_id: int) -> None:
        resp = self.session.delete(f"{self.api_base}/assets/{asset_id}", headers=self._headers(),
                                   timeout=self.timeout)
        if resp.status_code not in (200, 204, 404):
            self._check(resp, f"delete asset {asset_id}")

    def create_asset(self, name: str, asset_type: str, source_type: str,
                     description: str = "") -> Dict[str, Any]:
        body = {"name": name, "description": description, "type": asset_type,
                "options": {"sourceType": source_type}}
        resp = self.session.post(f"{self.api_base}/assets", json=body,
                                 headers=self._headers(json_body=True), timeout=self.timeout)
        self._check(resp, f"create asset {name!r}")
        return resp.json()

    # -- upload ---------------------------------------------------------------
    def upload_s3(self, upload_location: Dict[str, Any], file_path: Path,
                  log: Optional[logging.Logger] = None) -> bool:
        try:
            import boto3
            from boto3.s3.transfer import TransferConfig
        except ImportError:
            if log:
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
            key = upload_location.get("prefix", "") + file_path.name
            if log:
                mb = file_path.stat().st_size / (1024 * 1024)
                log.info(f"  S3 upload: {file_path.name} ({mb:.0f} MB) -> s3://{bucket}/{key}")
            s3.upload_file(
                str(file_path), bucket, key,
                ExtraArgs={"ContentType": "application/octet-stream"},
                Config=TransferConfig(multipart_threshold=100 * 1024 * 1024,
                                      multipart_chunksize=50 * 1024 * 1024,
                                      max_concurrency=4),
            )
            if log:
                log.info("  S3 upload complete")
            return True
        except Exception as e:
            if log:
                log.error(f"  S3 upload failed: {e}")
            return False

    def notify_complete(self, on_complete: Dict[str, Any]) -> None:
        url = on_complete["url"]
        method = on_complete.get("method", "POST").upper()
        fields = on_complete.get("fields", {})
        resp = self.session.request(method, url, json=fields, headers=self._headers(),
                                    timeout=self.timeout)
        if resp.status_code not in (200, 204):
            self._check(resp, "onComplete")

    def poll_ready(self, asset_id: int, timeout: int = 600, interval: float = 20.0,
                   log: Optional[logging.Logger] = None) -> bool:
        """Poll until COMPLETE (True) or a terminal error / timeout (False)."""
        deadline = time.monotonic() + timeout
        while True:
            try:
                data = self.get_asset(asset_id)
                status = data.get("status", "AWAITING_FILES")
                if log:
                    log.info(f"  ion asset {asset_id} status: {status}")
                if status == COMPLETE:
                    return True
                if status in TERMINAL_ERROR_STATUSES:
                    if log:
                        log.error(f"  ion tiling failed (status={status}): "
                                  f"{data.get('errorMessage', 'no details')}")
                    return False
            except Exception as e:
                if log:
                    log.warning(f"  Poll error: {e}")
            if time.monotonic() >= deadline:
                if log:
                    log.warning(f"  Timed out waiting for ion asset {asset_id}")
                return False
            self._sleep(interval)
