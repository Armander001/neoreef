"""TOCHICD land-use classification (国土数値情報 H23 土地利用) and Japanese era years.

This is the ONLY place the legend lives. The pipeline writes these values
into every GeoJSON feature and emits ``tochicd_legend.json`` from
:func:`legend_entries`; the viewers fetch that file instead of embedding a
copy. Labels/colours are the pipeline's historical table; extrude heights
(metres) come from the main viewer's table.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, TypedDict


class LanduseEntry(TypedDict):
    code: int
    name_ja: str
    name_en: str
    color: str        # "#RRGGBB"
    extrude_h: float  # metres, for the 3D extrusion in the viewers


def _e(code: int, name_ja: str, name_en: str, color: str, extrude_h: float) -> LanduseEntry:
    return {"code": code, "name_ja": name_ja, "name_en": name_en,
            "color": color, "extrude_h": extrude_h}


TOCHICD_MAP: Dict[int, LanduseEntry] = {
    0:  _e(0,  "田",             "Paddy field",          "#B5E853",  8),
    1:  _e(1,  "その他の農用地",   "Other agricultural",   "#FFFF99",  8),
    2:  _e(2,  "森林",            "Forest",               "#228B22", 25),
    3:  _e(3,  "荒地",            "Wasteland",            "#C2B280",  5),
    4:  _e(4,  "建物用地",         "Building land",        "#FF6347", 30),
    5:  _e(5,  "道路",            "Road",                 "#808080",  4),
    6:  _e(6,  "鉄道",            "Railway",              "#A0522D",  6),
    7:  _e(7,  "その他の用地",     "Other developed",      "#FFD700", 10),
    8:  _e(8,  "河川地及び湖沼",   "Rivers/lakes",         "#4169E1",  3),
    9:  _e(9,  "海浜",            "Beach/coastal",        "#F5DEB3",  3),
    10: _e(10, "海水域",          "Sea/ocean",            "#1E90FF",  2),
    11: _e(11, "ゴルフ場",        "Golf course",          "#90EE90", 12),
    12: _e(12, "公園・緑地",       "Park/green space",     "#7CFC00", 10),
    13: _e(13, "運動場",          "Sports ground",        "#ADFF2F", 10),
    14: _e(14, "工場・倉庫用地",   "Industrial/warehouse", "#CD853F", 35),
    15: _e(15, "公共施設用地",     "Public facilities",    "#DDA0DD", 18),
    16: _e(16, "学校用地",        "School land",          "#FFB6C1", 15),
    17: _e(17, "空地・その他",     "Vacant/other",         "#D3D3D3",  5),
    21: _e(21, "特殊地",          "Special zone",         "#9370DB", 12),
}

TOCHICD_DEFAULT: LanduseEntry = _e(-1, "不明", "Unknown", "#CCCCCC", 5)


def lookup(code) -> LanduseEntry:
    """Entry for a TOCHICD code; tolerant of None/str/float; falls back to Unknown."""
    try:
        return TOCHICD_MAP.get(int(code), TOCHICD_DEFAULT)
    except (TypeError, ValueError):
        return TOCHICD_DEFAULT


def legend_entries() -> List[LanduseEntry]:
    """Entries in code order, suitable for ``json.dump`` as tochicd_legend.json."""
    return [TOCHICD_MAP[k] for k in sorted(TOCHICD_MAP)]


# ---------------------------------------------------------------------------
# Japanese era years  (H23 -> 2011, R02 -> 2020)
# ---------------------------------------------------------------------------

ERA_OFFSETS: Dict[str, int] = {"M": 1867, "T": 1911, "S": 1925, "H": 1988, "R": 2018}

_ERA_RE = re.compile(r"^([MTSHR])(\d+)$", re.IGNORECASE)


def era_to_calendar(year_label: str) -> Optional[int]:
    """Convert an era label such as ``H23`` or ``r2`` to a calendar year.

    A plain four-digit year is returned as-is. Returns None (not 0) when the
    label cannot be interpreted, so callers can decide how to report it.
    """
    label = (year_label or "").strip()
    m = _ERA_RE.match(label)
    if m:
        return ERA_OFFSETS[m.group(1).upper()] + int(m.group(2))
    if label.isdigit():
        return int(label)
    return None
