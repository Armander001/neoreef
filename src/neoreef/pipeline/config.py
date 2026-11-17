"""Pipeline configuration: ``cesium_config.json`` -> :class:`PipelineConfig`.

Two Cesium ion tokens
---------------------
``CESIUM_ION_WRITE_TOKEN``   used by the upload stage only (assets:write). Never
                             leaves the machine running the pipeline.
``CESIUM_ION_VIEWER_TOKEN``  a *read-only* token (assets:read) that is published
                             in manifest.json for the browser viewers.
``CESIUM_ION_TOKEN``         deprecated alias for the write token; accepted
                             with a warning. It is never published.

Survey positions
----------------
Underwater surveys have no GPS, so 3D models need a hand-entered location:
``SURVEY_POSITIONS`` (inline object) or ``SURVEY_POSITIONS_FILE`` (path,
relative to the config file). If neither is set, ``survey_positions.json``
next to the config file is used when present. Shape::

    { "Ishi25_S008_0915_A1": {"lon": 124.2, "lat": 24.4, "height": -3, "heading_deg": 0} }
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from neoreef.common.naming import SURVEY_PATTERN_STR

PLACEHOLDER_TOKENS = {"", "YOUR_ION_ACCESS_TOKEN_HERE", "YOUR_READ_ONLY_TOKEN_HERE"}
REQUIRED_KEYS = ("OUTPUT_BASE", "LANDUSE_DIR", "CESIUM_OUTPUT_DIR")
DEFAULT_POSITIONS_FILENAME = "survey_positions.json"


class ConfigError(ValueError):
    """Raised for a config file that cannot be used."""


@dataclass
class PipelineConfig:
    output_base: Path
    landuse_dir: Path
    cesium_output_dir: Path

    ion_write_token: str = ""
    ion_viewer_token: str = ""
    use_ion: bool = True

    local_server_port: int = 8765
    server_base_url: str = ""
    shapefile_fallback_crs: str = "EPSG:6685"
    survey_pattern: str = SURVEY_PATTERN_STR
    continue_on_error: bool = True

    models_3d_dir: Optional[Path] = None
    extra_orthos: List[Dict[str, Any]] = field(default_factory=list)
    extra_3d_models: List[Dict[str, Any]] = field(default_factory=list)
    known_ion_assets: Dict[str, int] = field(default_factory=dict)
    base_ion_imagery_asset: Optional[int] = None
    base_ion_3dtiles_asset: Optional[int] = None
    survey_positions: Dict[str, Dict[str, float]] = field(default_factory=dict)

    viewers_dir: Optional[Path] = None
    source_path: Optional[Path] = None
    warnings: List[str] = field(default_factory=list)

    @property
    def has_write_token(self) -> bool:
        return self.ion_write_token not in PLACEHOLDER_TOKENS

    @property
    def has_viewer_token(self) -> bool:
        return self.ion_viewer_token not in PLACEHOLDER_TOKENS


def _opt_path(v) -> Optional[Path]:
    return Path(v) if v else None


def _token(v) -> str:
    v = (v or "").strip()
    return "" if v in PLACEHOLDER_TOKENS else v


def _load_positions(raw: Dict[str, Any], config_dir: Path, warnings: List[str]) -> Dict[str, Dict[str, float]]:
    inline = raw.get("SURVEY_POSITIONS")
    if isinstance(inline, dict):
        return {k: dict(v) for k, v in inline.items()}
    file_key = raw.get("SURVEY_POSITIONS_FILE")
    candidate = (config_dir / file_key) if file_key else (config_dir / DEFAULT_POSITIONS_FILENAME)
    if not candidate.exists():
        if file_key:
            warnings.append(f"SURVEY_POSITIONS_FILE not found: {candidate}")
        return {}
    try:
        with open(candidate, encoding="utf-8") as f:
            data = json.load(f)
        return {k: dict(v) for k, v in data.items() if not k.startswith("_")}
    except Exception as e:
        warnings.append(f"Could not read {candidate}: {e}")
        return {}


def config_from_dict(raw: Dict[str, Any], source_path: Optional[Path] = None) -> PipelineConfig:
    """Build a PipelineConfig from the parsed JSON object (comment keys allowed)."""
    raw = {k: v for k, v in raw.items() if not str(k).startswith("_")}
    missing = [k for k in REQUIRED_KEYS if not raw.get(k)]
    if missing:
        raise ConfigError(f"config is missing required key(s): {', '.join(missing)}")

    warnings: List[str] = []
    config_dir = source_path.parent if source_path else Path.cwd()

    write_token = _token(raw.get("CESIUM_ION_WRITE_TOKEN"))
    if not write_token and raw.get("CESIUM_ION_TOKEN"):
        write_token = _token(raw.get("CESIUM_ION_TOKEN"))
        if write_token:
            warnings.append("CESIUM_ION_TOKEN is deprecated: rename it to CESIUM_ION_WRITE_TOKEN "
                            "and add a read-only CESIUM_ION_VIEWER_TOKEN for the browser.")
    viewer_token = _token(raw.get("CESIUM_ION_VIEWER_TOKEN"))
    use_ion = bool(raw.get("USE_ION", True))
    if use_ion and not viewer_token:
        warnings.append("USE_ION is true but CESIUM_ION_VIEWER_TOKEN is not set: ion-hosted layers "
                        "will not load in the browser (the write token is never published).")

    cfg = PipelineConfig(
        output_base=Path(raw["OUTPUT_BASE"]),
        landuse_dir=Path(raw["LANDUSE_DIR"]),
        cesium_output_dir=Path(raw["CESIUM_OUTPUT_DIR"]),
        ion_write_token=write_token,
        ion_viewer_token=viewer_token,
        use_ion=use_ion,
        local_server_port=int(raw.get("LOCAL_SERVER_PORT", 8765)),
        server_base_url=str(raw.get("SERVER_BASE_URL", "") or "").rstrip("/"),
        shapefile_fallback_crs=raw.get("SHAPEFILE_FALLBACK_CRS", "EPSG:6685"),
        survey_pattern=raw.get("SURVEY_PATTERN") or SURVEY_PATTERN_STR,
        continue_on_error=bool(raw.get("CONTINUE_ON_ERROR", True)),
        models_3d_dir=_opt_path(raw.get("MODELS_3D_DIR")),
        extra_orthos=list(raw.get("EXTRA_ORTHOS", []) or []),
        extra_3d_models=list(raw.get("EXTRA_3D_MODELS", []) or []),
        known_ion_assets={str(k): int(v) for k, v in (raw.get("known_ion_assets") or {}).items()},
        base_ion_imagery_asset=raw.get("BASE_ION_IMAGERY_ASSET"),
        base_ion_3dtiles_asset=raw.get("BASE_ION_3DTILES_ASSET"),
        survey_positions=_load_positions(raw, config_dir, warnings),
        viewers_dir=_opt_path(raw.get("VIEWERS_DIR") or os.environ.get("NEOREEF_VIEWERS_DIR")),
        source_path=source_path,
        warnings=warnings,
    )
    return cfg


def load_config(config_path) -> PipelineConfig:
    p = Path(config_path)
    if not p.exists():
        raise ConfigError(f"config file not found: {p}  (copy config/cesium_config.example.json)")
    with open(p, encoding="utf-8") as f:
        raw = json.load(f)
    return config_from_dict(raw, source_path=p.resolve())
