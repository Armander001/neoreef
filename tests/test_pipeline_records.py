import json
from pathlib import Path

from neoreef.pipeline import state
from neoreef.pipeline.records import (
    LanduseRecord,
    Model3DRecord,
    OrthoRecord,
    RecordSet,
    carry_over,
)


def _sample() -> RecordSet:
    rs = RecordSet()
    rs.orthos.append(OrthoRecord("Ishi25_S008_0915_A1", "coral", Path("/in/a_coral_ortho.tif"),
                                 cog_path=Path("/out/cogs/x.tif"), bbox_wgs84=(1.0, 2.0, 3.0, 4.0),
                                 ion_asset_id=42))
    rs.orthos.append(OrthoRecord("Ishi25_S008_0915_A1", "drone", Path("/in/a_ortho.tif")))
    rs.landuse.append(LanduseRecord("H23", 2011, Path("/lu/Land-useMap_H23/TOCHI11.shp"),
                                    geojson_path=Path("/out/landuse/landuse_H23_TOCHI11.geojson"),
                                    feature_count=12, applied_crs="EPSG:6685"))
    rs.models.append(Model3DRecord("Ishi25_S008_0915_A1", "mesh", Path("/m/tileset.json"), "3dtiles",
                                   output_path=Path("/out/models/Ishi25_S008_0915_A1/tileset.json"),
                                   position={"lon": 124.2, "lat": 24.4, "height": -3.0, "heading_deg": 0.0},
                                   placed=True))
    rs.mark("cog")
    return rs


def test_ids():
    rs = _sample()
    assert rs.orthos[0].id == "Ishi25_S008_0915_A1:coral"
    assert rs.orthos[1].id == "Ishi25_S008_0915_A1:drone"
    assert rs.orthos[0].cog_filename == "Ishi25_S008_0915_A1_coral_cog.tif"
    assert rs.landuse[0].id == "landuse_H23_TOCHI11"
    assert rs.landuse[0].legacy_id == "landuse_H23"
    assert rs.models[0].id == "Ishi25_S008_0915_A1:mesh"


def test_roundtrip_through_json():
    rs = _sample()
    text = json.dumps(rs.to_dict(), ensure_ascii=False)
    back = RecordSet.from_dict(json.loads(text))
    assert back.to_dict() == rs.to_dict()
    assert isinstance(back.orthos[0].cog_path, Path)
    assert back.orthos[0].bbox_wgs84 == (1.0, 2.0, 3.0, 4.0)
    assert back.orthos[1].cog_path is None
    assert back.models[0].placed is True
    assert "cog" in back.generated_by


def test_from_dict_ignores_unknown_keys():
    d = {"survey_name": "X", "ortho_type": "drone", "src_path": "a.tif", "future_field": 1}
    rec = OrthoRecord.from_dict(d)
    assert rec.survey_name == "X" and rec.src_path == Path("a.tif")


def test_state_save_load_clear(tmp_path):
    rs = _sample()
    p = state.save_records(tmp_path, rs)
    assert p == tmp_path / ".state" / "records.json" and p.exists()
    loaded = state.load_records(tmp_path)
    assert loaded.to_dict() == rs.to_dict()
    state.clear_records(tmp_path)
    assert state.load_records(tmp_path).is_empty()


def test_state_load_corrupt_file_is_empty(tmp_path):
    p = state.state_path(tmp_path)
    p.parent.mkdir(parents=True)
    p.write_text("{not json", encoding="utf-8")
    assert state.load_records(tmp_path).is_empty()


def test_carry_over_keeps_ion_ids_by_id():
    old = _sample().orthos
    new = [OrthoRecord("Ishi25_S008_0915_A1", "coral", Path("/in/new.tif")),
           OrthoRecord("Ishi25_S008_0915_A1", "drone", Path("/in/new2.tif")),
           OrthoRecord("Ishi26_S001_0101_A1", "drone", Path("/in/new3.tif"))]
    carry_over(old, new)
    assert new[0].ion_asset_id == 42
    assert new[1].ion_asset_id is None
    assert new[2].ion_asset_id is None
