import re

import pytest

from neoreef.common import naming as n


# --- survey names -----------------------------------------------------------

@pytest.mark.parametrize("name", [
    "Ishi24_S001_0412_A1",
    "Ishi25_S008_0915_A1",
    "Ishi26_S120_1231_A9",   # any two-digit year (old batch regex rejected 26)
    "ishi25_s008_0915_a1",   # case-insensitive, like the old batch regex
])
def test_valid_survey_names(name):
    assert n.is_survey_name(name)


@pytest.mark.parametrize("name", [
    "Ishi2025_S008_0915_A1",      # 4-digit year
    "Ishi25_S08_0915_A1",         # 2-digit site
    "Ishi25_S008_915_A1",         # 3-digit date
    "Ishi25_S008_0915_A12",       # 2-digit attempt
    "Ishi25_S008_0915_A1_coral",  # suffix
    "Todoroki_Drone_1111_2024",   # non-standard (goes through EXTRA_ORTHOS)
    "",
])
def test_invalid_survey_names(name):
    assert not n.is_survey_name(name)
    assert n.parse_survey_name(name) is None


def test_parse_survey_name_components():
    s = n.parse_survey_name("Ishi25_S008_0915_A1")
    assert s is not None
    assert (s.year, s.site, s.month, s.day, s.attempt) == (2025, 8, 9, 15, 1)
    assert s.sort_key == (2025, 9, 15, 8, 1)
    assert s.raw == "Ishi25_S008_0915_A1"


def test_default_pattern_matches_config_pattern():
    """The regex shipped in cesium_config.example.json must accept the same names."""
    cfg = re.compile(r"^Ishi(?:\d{2})_S\d{3}_\d{4}_A\d$")
    for name in ["Ishi24_S001_0412_A1", "Ishi25_S008_0915_A1", "Ishi26_S001_0101_A2"]:
        assert bool(cfg.match(name)) == bool(n.SURVEY_PATTERN.match(name))


def test_compile_survey_pattern_override():
    p = n.compile_survey_pattern(r"^Site\d+$")
    assert p.match("Site12")
    assert not p.match("Ishi25_S008_0915_A1")
    assert n.compile_survey_pattern(None) is n.SURVEY_PATTERN
    assert n.compile_survey_pattern("") is n.SURVEY_PATTERN


def test_survey_folder_sort_matches_legacy_order():
    names = ["Ishi25_S010_0916_A1", "Ishi25_S001_0415_A1", "Ishi24_S003_0501_A1", "Ishi25_S001_0415_A2"]
    assert sorted(names, key=n.survey_folder_sort_key) == sorted(names)


# --- images -----------------------------------------------------------------

@pytest.mark.parametrize("fn", ["a.jpg", "a.JPG", "a.Jpg", "b.jpeg", "c.png", "d.ORF", "e.tif", "f.TIFF"])
def test_image_extensions_accepted(fn):
    assert n.is_image_file(fn)


@pytest.mark.parametrize("fn", ["a.txt", "a.psx", "a.jpg.bak", "jpg", ".jpg", "noext", "a.raw", "a.heic"])
def test_image_extensions_rejected(fn):
    assert not n.is_image_file(fn)


def test_image_extensions_cover_legacy_set():
    legacy = {".jpg", ".jpeg", ".JPG", ".JPEG", ".png", ".PNG", ".orf", ".ORF",
              ".tif", ".tiff", ".TIF", ".TIFF"}
    assert {e.lower() for e in legacy} == set(n.IMAGE_EXTENSIONS)


# --- orthos / cogs ------------------------------------------------------------

def test_ortho_filename_roundtrip():
    for t in n.ORTHO_TYPES:
        fn = n.ortho_filename("Ishi25_S008_0915_A1", t)
        assert n.parse_ortho_filename(fn) == ("Ishi25_S008_0915_A1", t)


def test_ortho_filename_matches_legacy_suffixes():
    assert n.ortho_filename("X", "drone") == "X_ortho.tif"
    assert n.ortho_filename("X", "coral") == "X_coral_ortho.tif"


def test_parse_ortho_filename_prefers_coral_over_drone():
    # "_coral_ortho.tif" also ends with "_ortho.tif"; coral must win.
    assert n.parse_ortho_filename("Ishi25_S008_0915_A1_coral_ortho.tif") == ("Ishi25_S008_0915_A1", "coral")


def test_parse_ortho_filename_accepts_paths_and_case():
    assert n.parse_ortho_filename(r"D:\Armando\Processed_Projects\Ishi25_S008_0915_A1_ORTHO.TIF") == ("Ishi25_S008_0915_A1", "drone")
    assert n.parse_ortho_filename("/x/y/Ishi25_S008_0915_A1_ortho.tif") == ("Ishi25_S008_0915_A1", "drone")


@pytest.mark.parametrize("fn", ["Ishi25_S008_0915_A1.tif", "Ishi25_S008_0915_A1_cog.tif", "ortho.tif", "x_ortho.tiff"])
def test_parse_ortho_filename_rejects(fn):
    assert n.parse_ortho_filename(fn) is None


def test_ortho_filename_rejects_unknown_type():
    with pytest.raises(ValueError):
        n.ortho_filename("X", "satellite")


def test_cog_filename_encodes_type_and_roundtrips():
    assert n.cog_filename("X", "drone") == "X_drone_cog.tif"
    assert n.cog_filename("X", "coral") == "X_coral_cog.tif"
    assert n.cog_filename("X", "drone") != n.cog_filename("X", "coral")
    assert n.parse_cog_filename("X_coral_cog.tif") == ("X", "coral")
    assert n.parse_cog_filename("cogs/X_drone_cog.tif") == ("X", "drone")


def test_parse_cog_filename_legacy_untyped():
    assert n.parse_cog_filename("Ishi25_S008_0915_A1_cog.tif") == ("Ishi25_S008_0915_A1", None)
    assert n.parse_cog_filename("Ishi25_S008_0915_A1_ortho.tif") is None


def test_ortho_id():
    assert n.ortho_id("X", "coral") == "X:coral"


# --- landuse / models -----------------------------------------------------------

def test_landuse_year_label():
    assert n.landuse_year_label("Land-useMap_H23") == "H23"
    assert n.landuse_year_label("Land-useMap_") is None
    assert n.landuse_year_label("PDF_H23") is None


def test_landuse_layer_id():
    assert n.landuse_layer_id("H23") == "landuse_H23"               # legacy id
    assert n.landuse_layer_id("H23", "TOCHI11") == "landuse_H23_TOCHI11"
    assert n.landuse_geojson_filename("landuse_H23") == "landuse_H23.geojson"


def test_model_names():
    assert n.model_id("X", "mesh") == "X:mesh"
    assert n.model_glb_filename("X") == "X_compressed.glb"
    assert n.TILESET_FILENAME == "tileset.json"
