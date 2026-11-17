import json
import re

import pytest

from neoreef.common import landuse_codes as lc

HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def test_every_entry_is_complete_and_self_keyed():
    for code, entry in lc.TOCHICD_MAP.items():
        assert entry["code"] == code
        assert entry["name_ja"] and entry["name_en"]
        assert HEX.match(entry["color"]), entry
        assert entry["extrude_h"] > 0


def test_codes_match_legacy_table():
    # The pipeline's historical table had exactly these 19 codes.
    assert sorted(lc.TOCHICD_MAP) == list(range(0, 18)) + [21]


def test_labels_match_legacy_pipeline_table():
    # Spot-check the codes that had drifted between the two viewers; the
    # pipeline's labels are canonical.
    assert lc.TOCHICD_MAP[12]["name_en"] == "Park/green space"
    assert lc.TOCHICD_MAP[13]["name_en"] == "Sports ground"
    assert lc.TOCHICD_MAP[15]["name_en"] == "Public facilities"
    assert lc.TOCHICD_MAP[16]["name_en"] == "School land"
    assert lc.TOCHICD_MAP[17]["name_en"] == "Vacant/other"


def test_extrude_heights_match_main_viewer():
    viewer = {0: 8, 1: 8, 2: 25, 3: 5, 4: 30, 5: 4, 6: 6, 7: 10, 8: 3, 9: 3, 10: 2,
              11: 12, 12: 10, 13: 10, 14: 35, 15: 18, 16: 15, 17: 5, 21: 12}
    assert {k: v["extrude_h"] for k, v in lc.TOCHICD_MAP.items()} == viewer


@pytest.mark.parametrize("raw,expected", [
    (4, 4), ("4", 4), (4.0, 4), ("21", 21),
    (None, -1), ("", -1), ("abc", -1), (99, -1), (-1, -1),
])
def test_lookup_is_tolerant(raw, expected):
    assert lc.lookup(raw)["code"] == expected


def test_legend_entries_are_sorted_and_json_serialisable():
    entries = lc.legend_entries()
    assert [e["code"] for e in entries] == sorted(lc.TOCHICD_MAP)
    text = json.dumps(entries, ensure_ascii=False)
    assert "田" in text and "#B5E853" in text


@pytest.mark.parametrize("label,year", [
    ("H23", 2011), ("h23", 2011), (" H23 ", 2011),
    ("R02", 2020), ("R2", 2020), ("r23", 2041),   # Reiwa parses (old regex had a stray space, not R)
    ("S60", 1985), ("T10", 1921), ("M45", 1912),
    ("2011", 2011),
])
def test_era_to_calendar(label, year):
    assert lc.era_to_calendar(label) == year


@pytest.mark.parametrize("label", ["", "X23", "H", "23H", None, "Heisei23"])
def test_era_to_calendar_unparseable(label):
    assert lc.era_to_calendar(label) is None
