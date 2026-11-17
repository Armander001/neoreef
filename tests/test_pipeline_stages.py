"""Stage tests that need no geospatial libraries (scan / placement / manifest / CLI)."""

import json
import logging
from pathlib import Path

import pytest

from neoreef.common.geodesy import geodetic_to_ecef
from neoreef.pipeline import cli, stages
from neoreef.pipeline.config import config_from_dict
from neoreef.pipeline.context import PipelineContext
from neoreef.pipeline.records import RecordSet
from neoreef.pipeline.stages import cog, landuse, manifest, model3d
from neoreef.pipeline.state import load_records


def _touch(p: Path, content=b"x"):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    return p


@pytest.fixture
def world(tmp_path):
    """OUTPUT_BASE / LANDUSE_DIR / MODELS_3D_DIR populated like a real run."""
    out_base = tmp_path / "Processed_Projects"
    _touch(out_base / "Ishi25_S008_0915_A1_ortho.tif")
    _touch(out_base / "Ishi25_S008_0915_A1_coral_ortho.tif")
    _touch(out_base / "Ishi25_S001_0415_A1_ortho.tif")
    _touch(out_base / "Ishi25_S001_0415_A1.psx")
    _touch(out_base / "Todoroki_Drone_1111_2024_ortho.tif")        # non-standard name
    _touch(out_base / "cesium_output" / "cogs" / "old_cog.tif")   # output tree, ignored

    lu = tmp_path / "LANDUSE"
    _touch(lu / "Land-useMap_H23" / "TOCHI11.shp")
    _touch(lu / "Land-useMap_H23" / "TOCHI11.dbf")
    _touch(lu / "Land-useMap_R02" / "A.shp")
    _touch(lu / "Land-useMap_R02" / "B.shp")
    _touch(lu / "PDF_H23" / "x.pdf")
    _touch(lu / "Land-useMap_EMPTY" / "readme.txt")

    models = out_base / "3d_models"
    _touch(models / "Ishi25_S008_0915_A1" / "Ishi25_S008_0915_A1_compressed.glb")
    (models / "Ishi25_S008_0915_A1" / "tileset.json").write_text(json.dumps({
        "asset": {"version": "1.1"}, "geometricError": 10,
        "root": {"boundingVolume": {"box": [0] * 12}, "geometricError": 0,
                 "content": {"uri": "Ishi25_S008_0915_A1_compressed.glb"}}}), encoding="utf-8")
    _touch(models / "loose" / "Other_model.glb")
    _touch(models / "unplaced" / "tileset.json", b'{"root": {}}')

    cfg = config_from_dict({
        "OUTPUT_BASE": str(out_base), "LANDUSE_DIR": str(lu),
        "CESIUM_OUTPUT_DIR": str(out_base / "cesium_output"),
        "MODELS_3D_DIR": str(models),
        "EXTRA_ORTHOS": [{"path": str(out_base / "Todoroki_Drone_1111_2024_ortho.tif"),
                          "survey_name": "Todoroki_Drone_1111_2024", "ortho_type": "drone"}],
        "SURVEY_POSITIONS": {"Ishi25_S008_0915_A1": {"lon": 124.2, "lat": 24.4, "height": -3, "heading_deg": 90}},
        "USE_ION": False,
    })
    log = logging.getLogger("test.stages")
    ctx = PipelineContext(cfg=cfg, log=log, out_dir=cfg.cesium_output_dir, viewers_dir=None, port=1)
    return ctx


# --- cog scan -------------------------------------------------------------------

def test_scan_orthomosaics_types_and_extras(world):
    recs = cog.scan_orthomosaics(world)
    assert [(r.survey_name, r.ortho_type) for r in recs] == [
        ("Ishi25_S001_0415_A1", "drone"),
        ("Ishi25_S008_0915_A1", "coral"),
        ("Ishi25_S008_0915_A1", "drone"),          # both types kept (legacy dropped the drone one)
        ("Todoroki_Drone_1111_2024", "drone"),     # via EXTRA_ORTHOS only
    ]


def test_cog_run_without_rasterio_keeps_records_and_state(world):
    rs = cog.run(world, RecordSet())
    assert len(rs.orthos) == 4
    assert all(r.cog_path is None for r in rs.orthos)   # conversion unavailable here
    assert "cog" in rs.generated_by


def test_cog_adopts_legacy_untyped_cog(world):
    legacy = world.cog_dir / "Ishi25_S001_0415_A1_cog.tif"
    _touch(legacy)
    rs = cog.run(world, RecordSet())
    rec = next(r for r in rs.orthos if r.survey_name == "Ishi25_S001_0415_A1")
    assert not legacy.exists()
    assert rec.cog_path == world.cog_dir / "Ishi25_S001_0415_A1_drone_cog.tif"
    assert rec.cog_path.exists()
    # ambiguous (survey with two orthos): left alone
    amb = _touch(world.cog_dir / "Ishi25_S008_0915_A1_cog.tif")
    cog.run(world, RecordSet())
    assert amb.exists()


# --- landuse scan ------------------------------------------------------------------

def test_scan_landuse_ids_and_years(world):
    recs = landuse.scan_landuse(world)
    assert [(r.id, r.calendar_year) for r in recs] == [
        ("landuse_H23_TOCHI11", 2011), ("landuse_R02_A", 2020), ("landuse_R02_B", 2020)]


def test_landuse_run_renames_legacy_geojson_only_when_unambiguous(world):
    legacy_h23 = _touch(world.landuse_out_dir / "landuse_H23.geojson", b"{}")
    legacy_r02 = _touch(world.landuse_out_dir / "landuse_R02.geojson", b"{}")
    rs = landuse.run(world, RecordSet())
    assert not legacy_h23.exists()
    assert (world.landuse_out_dir / "landuse_H23_TOCHI11.geojson").exists()
    assert legacy_r02.exists()                      # two shapefiles for R02: ambiguous
    assert [r.id for r in rs.landuse] == ["landuse_H23_TOCHI11"]   # others failed (no geopandas)


# --- model3d ---------------------------------------------------------------------

def test_model3d_places_tileset_and_skips_tileset_glb(world):
    rs = model3d.run(world, RecordSet())
    ids = sorted(r.id for r in rs.models)
    assert ids == ["Ishi25_S008_0915_A1:mesh", "Other_model:mesh", "unplaced:mesh"]

    placed = next(r for r in rs.models if r.survey_name == "Ishi25_S008_0915_A1")
    assert placed.placed is True
    assert placed.position == {"lon": 124.2, "lat": 24.4, "height": -3.0, "heading_deg": 90.0}
    ts = json.loads(placed.output_path.read_text(encoding="utf-8"))
    t = ts["root"]["transform"]
    assert len(t) == 16
    assert tuple(t[12:15]) == pytest.approx(geodetic_to_ecef(124.2, 24.4, -3.0))
    assert (world.models_out_dir / "Ishi25_S008_0915_A1" / "Ishi25_S008_0915_A1_compressed.glb").exists()

    loose = next(r for r in rs.models if r.survey_name == "Other_model")
    assert loose.format == "glb" and loose.placed is False
    assert (world.models_out_dir / "Other_model.glb").exists()
    assert not (world.models_out_dir / "Ishi25_S008_0915_A1_compressed.glb").exists()

    unplaced = next(r for r in rs.models if r.survey_name == "unplaced")
    assert unplaced.placed is False
    assert "transform" not in json.loads(unplaced.output_path.read_text())["root"]


def test_model3d_respects_existing_transform(world):
    src = world.cfg.models_3d_dir / "pre" / "tileset.json"
    _touch(src, json.dumps({"root": {"transform": [1] * 16}}).encode())
    rs = model3d.run(world, RecordSet())
    assert next(r for r in rs.models if r.survey_name == "pre").placed is True


# --- manifest --------------------------------------------------------------------

def test_manifest_stage_writes_files(world):
    rs = model3d.run(world, RecordSet())
    rs = manifest.run(world, rs)
    m = json.loads((world.out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert m["schema_version"] == 2 and m["use_ion"] is False
    assert len(m["models_3d"]) == 3
    legend = json.loads((world.out_dir / "tochicd_legend.json").read_text(encoding="utf-8"))
    assert legend["entries"][0]["name_en"] == "Paddy field"
    assert len(legend["entries"]) == 19


def test_manifest_copies_viewer_tree(world, tmp_path):
    v = tmp_path / "viewers"
    _touch(v / "index.html", b"<html>")
    _touch(v / "js" / "a.js", b"//")
    world.viewers_dir = v
    manifest.run(world, RecordSet())
    assert (world.out_dir / "index.html").exists() and (world.out_dir / "js" / "a.js").exists()


# --- stage registry + CLI -------------------------------------------------------------

def test_expand():
    assert stages.expand("all") == ["cog", "landuse", "model3d", "upload", "manifest"]
    assert stages.expand("serve") == []
    assert stages.expand("cog") == ["cog"]
    with pytest.raises(KeyError):
        stages.expand("nope")


def test_cli_end_to_end_persists_state(world, tmp_path):
    cfg_path = tmp_path / "config" / "cesium_config.json"
    cfg_path.parent.mkdir()
    raw = {
        "OUTPUT_BASE": str(world.cfg.output_base), "LANDUSE_DIR": str(world.cfg.landuse_dir),
        "CESIUM_OUTPUT_DIR": str(world.out_dir), "MODELS_3D_DIR": str(world.cfg.models_3d_dir),
        "USE_ION": False,
        "SURVEY_POSITIONS": world.cfg.survey_positions,
    }
    cfg_path.write_text(json.dumps(raw), encoding="utf-8")

    assert cli.main(["--config", str(cfg_path), "--stage", "cog"]) == 0
    rs = load_records(world.out_dir)
    assert len(rs.orthos) == 3 and not rs.models

    assert cli.main(["--config", str(cfg_path), "--stage", "model3d"]) == 0
    rs = load_records(world.out_dir)
    assert len(rs.orthos) == 3 and len(rs.models) == 3       # cog records survived

    assert cli.main(["--config", str(cfg_path), "--stage", "manifest"]) == 0
    m = json.loads((world.out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert [o["id"] for o in m["orthomosaics"]] == [
        "Ishi25_S001_0415_A1:drone", "Ishi25_S008_0915_A1:coral", "Ishi25_S008_0915_A1:drone"]
    assert m["models_3d"][0]["placed"] is True

    assert cli.main(["--config", str(cfg_path), "--stage", "manifest", "--rescan"]) == 0
    m = json.loads((world.out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert m["orthomosaics"] == []                           # state cleared, manifest alone finds nothing

    assert cli.main(["--config", str(tmp_path / "missing.json"), "--stage", "cog"]) == 2
