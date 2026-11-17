from datetime import datetime, timezone
from pathlib import Path

from neoreef.pipeline.config import config_from_dict
from neoreef.pipeline.manifest_schema import MANIFEST_SCHEMA_VERSION, build_manifest
from neoreef.pipeline.records import LanduseRecord, Model3DRecord, OrthoRecord, RecordSet

BASE = {"OUTPUT_BASE": "/in", "LANDUSE_DIR": "/lu", "CESIUM_OUTPUT_DIR": "/out"}
WHEN = datetime(2026, 11, 16, 5, 0, 0, tzinfo=timezone.utc)


def _rs() -> RecordSet:
    rs = RecordSet()
    rs.orthos.append(OrthoRecord("S1", "coral", Path("/in/S1_coral_ortho.tif"),
                                 cog_path=Path("/out/cogs/S1_coral_cog.tif"),
                                 preview_path=Path("/out/previews/S1_coral.png"),
                                 bbox_wgs84=(124.1, 24.4, 124.2, 24.5)))
    rs.orthos.append(OrthoRecord("S1", "drone", Path("/in/S1_ortho.tif"), cog_path=Path("/out/cogs/S1_drone_cog.tif")))
    rs.landuse.append(LanduseRecord("H23", 2011, Path("/lu/Land-useMap_H23/TOCHI11.shp"),
                                    geojson_path=Path("/out/landuse/landuse_H23_TOCHI11.geojson"), feature_count=7))
    rs.models.append(Model3DRecord("S1", "mesh", Path("/m/tileset.json"), "3dtiles",
                                   output_path=Path("/out/models/S1/tileset.json"),
                                   position={"lon": 1.0, "lat": 2.0, "height": 0.0, "heading_deg": 0.0}, placed=True))
    rs.models.append(Model3DRecord("S2", "mesh", Path("/m/S2.glb"), "glb", output_path=Path("/out/models/S2.glb")))
    return rs


def test_golden_shape():
    cfg = config_from_dict({**BASE, "CESIUM_ION_WRITE_TOKEN": "w" * 30, "CESIUM_ION_VIEWER_TOKEN": "v" * 30,
                            "BASE_ION_3DTILES_ASSET": 2275207})
    m = build_manifest(_rs(), cfg, generated=WHEN)
    assert m == {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "generated": "2026-11-16T05:00:00Z",
        "viewer_ion_token": "v" * 30,
        "use_ion": True,
        "base_ion_imagery_asset": None,
        "base_ion_3dtiles_asset": 2275207,
        "legend_url": "tochicd_legend.json",
        "survey_area": {"name": "Ishigaki Island", "center_lon": 124.205, "center_lat": 24.470,
                        "default_altitude_m": 15000},
        "orthomosaics": [
            {"id": "S1:coral", "survey_name": "S1", "ortho_type": "coral",
             "bbox_wgs84": [124.1, 24.4, 124.2, 24.5], "ion_asset_id": None,
             "cog_url": "cogs/S1_coral_cog.tif", "preview_url": "previews/S1_coral.png"},
            {"id": "S1:drone", "survey_name": "S1", "ortho_type": "drone",
             "bbox_wgs84": None, "ion_asset_id": None,
             "cog_url": "cogs/S1_drone_cog.tif", "preview_url": None},
        ],
        "landuse_layers": [
            {"id": "landuse_H23_TOCHI11", "year_label": "H23", "calendar_year": 2011, "feature_count": 7,
             "ion_asset_id": None, "geojson_url": "landuse/landuse_H23_TOCHI11.geojson"},
        ],
        "models_3d": [
            {"id": "S1:mesh", "survey_name": "S1", "model_type": "mesh", "format": "3dtiles",
             "ion_asset_id": None, "position": {"lon": 1.0, "lat": 2.0, "height": 0.0, "heading_deg": 0.0},
             "placed": True, "tileset_url": "models/S1/tileset.json"},
            {"id": "S2:mesh", "survey_name": "S2", "model_type": "mesh", "format": "glb",
             "ion_asset_id": None, "position": None, "placed": False, "gltf_url": "models/S2.glb"},
        ],
    }


def test_write_token_never_published():
    cfg = config_from_dict({**BASE, "CESIUM_ION_TOKEN": "secretwrite" * 3})
    m = build_manifest(_rs(), cfg, generated=WHEN)
    text = str(m)
    assert "secretwrite" not in text
    assert m["viewer_ion_token"] == ""
    assert "cesium_ion_token" not in m


def test_viewer_token_blank_when_ion_disabled():
    cfg = config_from_dict({**BASE, "USE_ION": False, "CESIUM_ION_VIEWER_TOKEN": "v" * 30})
    m = build_manifest(_rs(), cfg, generated=WHEN)
    assert m["use_ion"] is False and m["viewer_ion_token"] == ""


def test_known_ion_assets_fallbacks():
    cfg = config_from_dict({**BASE, "known_ion_assets": {"S1": 11, "landuse_H23": 22}})
    m = build_manifest(_rs(), cfg, generated=WHEN)
    assert m["orthomosaics"][0]["ion_asset_id"] == 11      # by survey name (legacy key)
    assert m["landuse_layers"][0]["ion_asset_id"] == 22    # by legacy layer id
    cfg2 = config_from_dict({**BASE, "known_ion_assets": {"S1:coral": 33}})
    assert build_manifest(_rs(), cfg2, generated=WHEN)["orthomosaics"][0]["ion_asset_id"] == 33


def test_server_base_url_prefixes_all_urls():
    cfg = config_from_dict({**BASE, "SERVER_BASE_URL": "http://h/neoreef/"})
    m = build_manifest(_rs(), cfg, generated=WHEN)
    assert m["legend_url"] == "http://h/neoreef/tochicd_legend.json"
    assert m["orthomosaics"][0]["cog_url"] == "http://h/neoreef/cogs/S1_coral_cog.tif"
    assert m["orthomosaics"][0]["preview_url"] == "http://h/neoreef/previews/S1_coral.png"
    assert m["landuse_layers"][0]["geojson_url"] == "http://h/neoreef/landuse/landuse_H23_TOCHI11.geojson"
    assert m["models_3d"][0]["tileset_url"] == "http://h/neoreef/models/S1/tileset.json"
    assert m["models_3d"][1]["gltf_url"] == "http://h/neoreef/models/S2.glb"
