"""Survey, orthomosaic, COG, land-use and model naming conventions.

Single source of truth for every filename pattern the batch script and the
pipeline agree on. Nothing here touches the filesystem.

Survey folder convention (field surveys, Ishigaki):
    Ishi{YY}_S{NNN}_{MMDD}_A{N}      e.g. Ishi25_S008_0915_A1
        YY   two-digit survey year (2025 -> 25)
        NNN  site number
        MMDD month and day of the survey
        N    attempt / pass number

Metashape outputs (written to OUTPUT_BASE by neoreef.metashape.batch):
    {survey}_ortho.tif               drone / top-down orthomosaic
    {survey}_coral_ortho.tif         coral (underwater) orthomosaic

Pipeline outputs (written to CESIUM_OUTPUT_DIR):
    cogs/{survey}_{ortho_type}_cog.tif
    landuse/landuse_{year_label}_{stem}.geojson
    models/{survey}/tileset.json
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Pattern, Tuple

# ---------------------------------------------------------------------------
# Survey folders
# ---------------------------------------------------------------------------

#: Default survey-name regex. Accepts any two-digit year (the old batch script
#: hard-coded 24|25, which silently skipped later seasons). Case-insensitive to
#: match the batch script's historical behaviour.
SURVEY_PATTERN_STR = r"^Ishi(?P<yy>\d{2})_S(?P<site>\d{3})_(?P<mm>\d{2})(?P<dd>\d{2})_A(?P<attempt>\d)$"
SURVEY_PATTERN: Pattern[str] = re.compile(SURVEY_PATTERN_STR, re.IGNORECASE)

#: Pivot for expanding two-digit survey years. Surveys started in 2024.
SURVEY_CENTURY = 2000


def compile_survey_pattern(pattern: Optional[str] = None) -> Pattern[str]:
    """Return a compiled survey regex, honouring a config override if given."""
    if not pattern:
        return SURVEY_PATTERN
    return re.compile(pattern, re.IGNORECASE)


@dataclass(frozen=True)
class SurveyName:
    """Parsed components of a survey folder name."""

    raw: str
    year: int        # four-digit, e.g. 2025
    site: int        # e.g. 8 for S008
    month: int
    day: int
    attempt: int

    @property
    def sort_key(self) -> Tuple[int, int, int, int, int]:
        """Chronological key: (year, month, day, site, attempt)."""
        return (self.year, self.month, self.day, self.site, self.attempt)


def parse_survey_name(name: str) -> Optional[SurveyName]:
    """Parse ``Ishi25_S008_0915_A1`` into its parts; None if it doesn't match.

    Only the default pattern (with named groups) can be parsed. A custom
    SURVEY_PATTERN from config may still *match* via :func:`is_survey_name`.
    """
    m = SURVEY_PATTERN.match(name.strip())
    if not m:
        return None
    return SurveyName(
        raw=name.strip(),
        year=SURVEY_CENTURY + int(m.group("yy")),
        site=int(m.group("site")),
        month=int(m.group("mm")),
        day=int(m.group("dd")),
        attempt=int(m.group("attempt")),
    )


def is_survey_name(name: str, pattern: Optional[Pattern[str]] = None) -> bool:
    """True if *name* matches the survey convention (or the supplied pattern)."""
    return bool((pattern or SURVEY_PATTERN).match(name))


def survey_folder_sort_key(name: str) -> str:
    """Key used to order survey folders for batch processing.

    Case-insensitive lexicographic order. For names that follow the
    convention this is identical to the historical ``sorted(Path)`` order.
    """
    return name.lower()


# ---------------------------------------------------------------------------
# Images (Metashape input)
# ---------------------------------------------------------------------------

#: Lowercase image extensions accepted as Metashape input. Compare against
#: ``path.suffix.lower()``. Equivalent to the old explicit upper/lower set,
#: and additionally tolerant of mixed case such as ``.Jpg``.
IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".orf", ".tif", ".tiff"})


def is_image_file(filename: str) -> bool:
    """True if *filename* has an accepted image extension (case-insensitive)."""
    dot = filename.rfind(".")
    if dot <= 0:
        return False
    return filename[dot:].lower() in IMAGE_EXTENSIONS


# ---------------------------------------------------------------------------
# Orthomosaics
# ---------------------------------------------------------------------------

ORTHO_TYPES = ("drone", "coral")

#: Filename suffix per ortho type. Order matters: the more specific suffix
#: (coral) must be tested before the generic one (drone).
ORTHO_SUFFIXES = (
    ("coral", "_coral_ortho.tif"),
    ("drone", "_ortho.tif"),
)


def ortho_filename(survey_name: str, ortho_type: str) -> str:
    """``Ishi25_S008_0915_A1`` + ``coral`` -> ``Ishi25_S008_0915_A1_coral_ortho.tif``."""
    for t, suffix in ORTHO_SUFFIXES:
        if t == ortho_type:
            return survey_name + suffix
    raise ValueError(f"unknown ortho_type {ortho_type!r}; expected one of {ORTHO_TYPES}")


def parse_ortho_filename(filename: str) -> Optional[Tuple[str, str]]:
    """Return ``(survey_name, ortho_type)`` for a Metashape ortho file, else None.

    Only the basename is inspected. Does not validate the survey name; use
    :func:`is_survey_name` on the first element for that.
    """
    base = filename.replace("\\", "/").rsplit("/", 1)[-1]
    lower = base.lower()
    for ortho_type, suffix in ORTHO_SUFFIXES:
        if lower.endswith(suffix):
            return base[: -len(suffix)], ortho_type
    return None


def cog_filename(survey_name: str, ortho_type: str) -> str:
    """Type-encoded COG name: ``{survey}_{type}_cog.tif``.

    Encoding the type prevents a survey with both a drone and a coral ortho
    from overwriting itself (the legacy ``{survey}_cog.tif`` did).
    """
    if ortho_type not in ORTHO_TYPES:
        raise ValueError(f"unknown ortho_type {ortho_type!r}; expected one of {ORTHO_TYPES}")
    return f"{survey_name}_{ortho_type}_cog.tif"


def parse_cog_filename(filename: str) -> Optional[Tuple[str, Optional[str]]]:
    """Inverse of :func:`cog_filename`, tolerant of the legacy untyped name.

    Returns ``(survey_name, ortho_type)``; ``ortho_type`` is None for a legacy
    ``{survey}_cog.tif`` produced before the type was encoded.
    """
    base = filename.replace("\\", "/").rsplit("/", 1)[-1]
    if not base.lower().endswith("_cog.tif"):
        return None
    stem = base[: -len("_cog.tif")]
    for t in ORTHO_TYPES:
        if stem.lower().endswith("_" + t):
            return stem[: -(len(t) + 1)], t
    return stem, None


def ortho_id(survey_name: str, ortho_type: str) -> str:
    """Manifest id for an ortho layer: ``{survey}:{type}``."""
    return f"{survey_name}:{ortho_type}"


# ---------------------------------------------------------------------------
# Land use
# ---------------------------------------------------------------------------

#: Land-use source folders look like ``Land-useMap_H23``.
LANDUSE_DIR_PREFIX = "Land-useMap_"


def landuse_year_label(dirname: str) -> Optional[str]:
    """``Land-useMap_H23`` -> ``H23``; None if the folder is not a land-use map."""
    if not dirname.startswith(LANDUSE_DIR_PREFIX):
        return None
    label = dirname[len(LANDUSE_DIR_PREFIX):].strip()
    return label or None


def landuse_layer_id(year_label: str, stem: Optional[str] = None) -> str:
    """Layer id for a land-use GeoJSON.

    Including the shapefile stem keeps two shapefiles in one year folder from
    colliding. Pass ``stem=None`` for the legacy ``landuse_{year}`` id.
    """
    return f"landuse_{year_label}" if not stem else f"landuse_{year_label}_{stem}"


def landuse_geojson_filename(layer_id: str) -> str:
    return f"{layer_id}.geojson"


# ---------------------------------------------------------------------------
# 3D models
# ---------------------------------------------------------------------------

MODEL_TYPES = ("mesh", "pointcloud")
MODEL_FORMATS = ("3dtiles", "gltf", "glb")

#: Name of the compressed glb that neoreef.metashape.export_model writes.
MODEL_GLB_SUFFIX = "_compressed.glb"
TILESET_FILENAME = "tileset.json"
SURVEY_META_FILENAME = "survey_meta.json"


def model_id(survey_name: str, model_type: str) -> str:
    """Manifest id for a 3D model: ``{survey}:{model_type}``."""
    return f"{survey_name}:{model_type}"


def model_glb_filename(survey_name: str) -> str:
    return survey_name + MODEL_GLB_SUFFIX
