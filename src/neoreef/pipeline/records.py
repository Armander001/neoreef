"""Pipeline records: what the stages know about each input and its outputs.

Records are plain dataclasses that round-trip through JSON (``state.py``)
so a stage run on Monday can be picked up by a different stage on Friday
without re-scanning or guessing.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type, TypeVar

from neoreef.common.naming import (
    cog_filename,
    landuse_layer_id,
    model_id,
    ortho_id,
)

T = TypeVar("T", bound="PathRecord")

RECORDS_SCHEMA_VERSION = 1


class PathRecord:
    """Mixin: JSON (de)serialisation with ``Path`` fields coerced to/from str."""

    PATH_FIELDS: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        d = dataclasses.asdict(self)  # type: ignore[call-overload]
        for k in self.PATH_FIELDS:
            v = d.get(k)
            d[k] = str(v) if v is not None else None
        return d

    @classmethod
    def from_dict(cls: Type[T], d: Dict[str, Any]) -> T:
        known = {f.name for f in fields(cls)}  # type: ignore[arg-type]
        kw = {k: v for k, v in d.items() if k in known}
        for k in cls.PATH_FIELDS:
            if kw.get(k) is not None:
                kw[k] = Path(kw[k])
        if kw.get("bbox_wgs84") is not None:
            kw["bbox_wgs84"] = tuple(kw["bbox_wgs84"])
        return cls(**kw)  # type: ignore[call-arg]


@dataclass
class OrthoRecord(PathRecord):
    survey_name: str
    ortho_type: str                     # "drone" | "coral"
    src_path: Path
    cog_path: Optional[Path] = None
    preview_path: Optional[Path] = None # browser-decodable PNG for the local fallback
    ion_asset_id: Optional[int] = None
    bbox_wgs84: Optional[Tuple[float, float, float, float]] = None  # W,S,E,N

    PATH_FIELDS = ("src_path", "cog_path", "preview_path")

    @property
    def id(self) -> str:
        return ortho_id(self.survey_name, self.ortho_type)

    @property
    def cog_filename(self) -> str:
        return cog_filename(self.survey_name, self.ortho_type)


@dataclass
class LanduseRecord(PathRecord):
    year_label: str                     # e.g. "H23"
    calendar_year: int                  # e.g. 2011 (0 if unknown)
    shp_path: Path
    geojson_path: Optional[Path] = None
    ion_asset_id: Optional[int] = None
    feature_count: int = 0
    applied_crs: str = ""

    PATH_FIELDS = ("shp_path", "geojson_path")

    @property
    def id(self) -> str:
        """``landuse_{year}_{shapefile stem}`` so two shapefiles per year don't collide."""
        return landuse_layer_id(self.year_label, self.shp_path.stem)

    @property
    def legacy_id(self) -> str:
        return landuse_layer_id(self.year_label)


@dataclass
class Model3DRecord(PathRecord):
    survey_name: str
    model_type: str = "mesh"            # "mesh" | "pointcloud"
    src_path: Optional[Path] = None
    format: str = ""                    # "3dtiles" | "gltf" | "glb"
    output_path: Optional[Path] = None
    ion_asset_id: Optional[int] = None
    position: Optional[Dict[str, float]] = None  # {lon, lat, height, heading_deg}
    placed: bool = False                # True once a globe transform is known

    PATH_FIELDS = ("src_path", "output_path")

    @property
    def id(self) -> str:
        return model_id(self.survey_name, self.model_type)


@dataclass
class RecordSet:
    orthos: List[OrthoRecord] = field(default_factory=list)
    landuse: List[LanduseRecord] = field(default_factory=list)
    models: List[Model3DRecord] = field(default_factory=list)
    generated_by: Dict[str, str] = field(default_factory=dict)  # stage -> ISO timestamp

    # -- bookkeeping ---------------------------------------------------------
    def mark(self, stage: str) -> None:
        self.generated_by[stage] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def is_empty(self) -> bool:
        return not (self.orthos or self.landuse or self.models)

    # -- serialisation -------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": RECORDS_SCHEMA_VERSION,
            "generated_by": dict(self.generated_by),
            "orthos": [r.to_dict() for r in self.orthos],
            "landuse": [r.to_dict() for r in self.landuse],
            "models": [r.to_dict() for r in self.models],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RecordSet":
        return cls(
            orthos=[OrthoRecord.from_dict(x) for x in d.get("orthos", [])],
            landuse=[LanduseRecord.from_dict(x) for x in d.get("landuse", [])],
            models=[Model3DRecord.from_dict(x) for x in d.get("models", [])],
            generated_by=dict(d.get("generated_by", {})),
        )


def carry_over(old: list, new: list, attrs: Tuple[str, ...] = ("ion_asset_id",)) -> None:
    """Copy *attrs* from records in *old* onto same-id records in *new* when unset.

    Lets a fresh scan keep the ion asset ids (etc.) a previous run obtained.
    """
    by_id = {r.id: r for r in old}
    for rec in new:
        prev = by_id.get(rec.id)
        if prev is None:
            continue
        for a in attrs:
            if getattr(rec, a) in (None, 0, "") and getattr(prev, a) not in (None, 0, ""):
                setattr(rec, a, getattr(prev, a))
