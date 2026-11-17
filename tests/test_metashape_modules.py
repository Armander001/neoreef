"""Metashape batch modules, exercised with a stand-in ``Metashape`` module."""

import json
import sys
import types
from pathlib import Path

import pytest

from neoreef.metashape import export_model, export_preview, processing
from neoreef.metashape.config import MetashapeConfig, enum


# --- a minimal fake of the Metashape API ---------------------------------------

class _Coord:
    def __init__(self, x, y, z): self.x, self.y, self.z = x, y, z


class _Vertex:
    def __init__(self, x, y, z): self.coord = _Coord(x, y, z)


class _Model:
    def __init__(self, verts): self.vertices = [_Vertex(*v) for v in verts]


class FakeChunk:
    def __init__(self):
        self.label = ""
        self.cameras = []
        self.calls = []
        self.model = _Model([(0, 0, 0), (2, 4, 6), (-2, 1, 3)])
        self.fail_first_jpeg = False
        self.crs = None

    def _rec(self, name, *a, **k): self.calls.append((name, a, k))

    def addPhotos(self, paths): self._rec("addPhotos", paths); self.cameras = list(paths)
    def matchPhotos(self, **k): self._rec("matchPhotos", **k)
    def alignCameras(self): self._rec("alignCameras")
    def optimizeCameras(self): self._rec("optimizeCameras")
    def buildDepthMaps(self, **k): self._rec("buildDepthMaps", **k)
    def buildModel(self, **k): self._rec("buildModel", **k)
    def buildOrthomosaic(self, **k): self._rec("buildOrthomosaic", **k)

    def exportOrthomosaic(self, path, **k):
        self._rec("exportOrthomosaic", path, **k)
        if k.get("image_format") == "JPEG" and self.fail_first_jpeg and "white_background" not in k:
            raise RuntimeError("no projection")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(b"img")

    def exportModel(self, path, **k):
        self._rec("exportModel", path, **k)
        Path(path).write_text("obj")
        Path(path).with_suffix(".mtl").write_text("mtl")


class FakeDocument:
    instances = []

    def __init__(self):
        self.chunk = None
        self.saved = []
        FakeDocument.instances.append(self)

    def open(self, path): self.path = path; self.chunk = FakeChunk()
    def save(self, path=None): self.saved.append(path)
    def addChunk(self): self.chunk = FakeChunk(); return self.chunk


@pytest.fixture
def fake_metashape(monkeypatch):
    m = types.ModuleType("Metashape")
    m.Document = FakeDocument
    m.CoordinateSystem = lambda s: ("CRS", s)
    m.ImageFormatJPEG = "JPEG"
    m.ImageFormatTIFF = "TIFF"
    m.ModelFormatOBJ = "OBJ"
    m.DepthMapsData = "DepthMapsData"
    m.ModelData = "ModelData"
    m.MildFiltering = "MildFiltering"
    m.Arbitrary = "Arbitrary"
    m.EnabledInterpolation = "EnabledInterpolation"
    m.MosaicBlending = "MosaicBlending"
    m.app = types.SimpleNamespace(settings=types.SimpleNamespace(project_absolute_paths=False),
                                  console=types.SimpleNamespace(print=lambda s: None))
    monkeypatch.setitem(sys.modules, "Metashape", m)
    FakeDocument.instances.clear()
    return m


def _cfg(tmp_path, **kw):
    lib = tmp_path / "lib"
    lib.mkdir(exist_ok=True)
    return MetashapeConfig(photo_library=lib, output_base=tmp_path / "out", **kw)


# --- config ----------------------------------------------------------------------

def test_config_paths_and_defaults(tmp_path):
    cfg = _cfg(tmp_path)
    assert cfg.year_root == cfg.photo_library
    assert cfg.models_dir == tmp_path / "out" / "3d_models"
    assert cfg.gltfpack_args == ["-cc", "-tc"]
    assert "FULL YEAR" in cfg.mode_label()
    cfg2 = _cfg(tmp_path, target_folder=str(tmp_path / "lib"), year_root=str(tmp_path))
    assert isinstance(cfg2.target_folder, Path) and cfg2.year_root == tmp_path
    assert "SINGLE FOLDER" in cfg2.mode_label()


def test_config_problems(tmp_path):
    cfg = MetashapeConfig(photo_library=tmp_path / "nope", output_base=tmp_path, jpeg_quality=0)
    probs = cfg.problems()
    assert any("PHOTO_LIBRARY" in p for p in probs) and any("JPEG_QUALITY" in p for p in probs)
    assert _cfg(tmp_path).problems() == []


def test_enum_resolution(fake_metashape):
    assert enum(fake_metashape, "MildFiltering") == "MildFiltering"
    with pytest.raises(ValueError, match="NoSuchThing"):
        enum(fake_metashape, "NoSuchThing")


# --- export_model (pure parts) ----------------------------------------------------

def test_compute_model_bbox_single_pass():
    bbox = export_model.compute_model_bbox(FakeChunk())
    assert bbox == {"x_min": -2, "x_max": 2, "y_min": 0, "y_max": 4, "z_min": 0, "z_max": 6}
    empty = FakeChunk(); empty.model = None
    with pytest.raises(ValueError):
        export_model.compute_model_bbox(empty)


def test_make_tileset_geometry():
    ts = export_model.make_tileset("m.glb", {"x_min": -2, "x_max": 2, "y_min": 0, "y_max": 4, "z_min": 0, "z_max": 6})
    assert ts["asset"]["version"] == "1.1"
    assert ts["root"]["content"]["uri"] == "m.glb"
    assert ts["root"]["boundingVolume"]["box"] == [0, 2, 3, 2, 0, 0, 0, 2, 0, 0, 0, 3]
    assert ts["geometricError"] == 6.0
    assert "transform" not in ts["root"]


def test_run_tool_success_failure_missing(tmp_path):
    msgs = []
    py = sys.executable
    assert export_model.run_tool([py, "-c", "print('hi')"], msgs.append, "py") is True
    assert any("hi" in m for m in msgs)
    assert export_model.run_tool([py, "-c", "import sys; sys.exit(3)"], msgs.append, "py") is False
    assert any("exit 3" in m for m in msgs)
    assert export_model.run_tool(["definitely-not-a-real-tool-xyz"], msgs.append, "nope") is False
    assert any("not found" in m for m in msgs)


def test_write_survey_meta(tmp_path):
    p = export_model.write_survey_meta(tmp_path, "S1", {"x_min": 0, "x_max": 1, "y_min": 0, "y_max": 1, "z_min": 0, "z_max": 1}, "S1_compressed.glb", None)
    meta = json.loads(p.read_text())
    assert p.name == "survey_meta.json"
    assert meta["survey_name"] == "S1" and meta["crs"] is None and meta["glb"] == "S1_compressed.glb"


def test_export_3d_model_with_stub_tools(tmp_path, fake_metashape, monkeypatch):
    # Stand in for obj2gltf / gltfpack: "convert" by copying the input to the output path.
    def fake_run_tool(cmd, log, label="tool", timeout=600):
        src, dst = Path(cmd[cmd.index("-i") + 1]), Path(cmd[cmd.index("-o") + 1])
        dst.write_bytes(src.read_bytes() + label.encode())
        return True
    monkeypatch.setattr(export_model, "run_tool", fake_run_tool)
    cfg = _cfg(tmp_path, export_3d_model=True)
    msgs = []
    ts = export_model.export_3d_model(FakeChunk(), "S1", tmp_path / "m" / "S1", cfg, msgs.append)
    assert ts == tmp_path / "m" / "S1" / "tileset.json"
    files = sorted(p.name for p in ts.parent.iterdir())
    assert files == ["S1_compressed.glb", "survey_meta.json", "tileset.json"]   # obj/mtl/raw glb cleaned
    assert json.loads(ts.read_text())["root"]["content"]["uri"] == "S1_compressed.glb"


def test_export_3d_model_gltfpack_failure_falls_back_to_raw_glb(tmp_path, fake_metashape, monkeypatch):
    def fake_run_tool(cmd, log, label="tool", timeout=600):
        if label == "gltfpack":
            return False
        Path(cmd[cmd.index("-o") + 1]).write_bytes(b"glb")
        return True
    monkeypatch.setattr(export_model, "run_tool", fake_run_tool)
    ts = export_model.export_3d_model(FakeChunk(), "S1", tmp_path / "m", _cfg(tmp_path), lambda s: None)
    assert json.loads(ts.read_text())["root"]["content"]["uri"] == "S1.glb"
    assert (tmp_path / "m" / "S1.glb").exists()


# --- export_preview -------------------------------------------------------------

def test_jpeg_preview_fallback(tmp_path, fake_metashape):
    chunk = FakeChunk()
    chunk.fail_first_jpeg = True
    out = export_preview.export_jpeg_preview(chunk, tmp_path / "S1.jpg", 90, lambda s: None)
    assert out == tmp_path / "S1_render.jpg" and out.exists()
    chunk2 = FakeChunk()
    assert export_preview.export_jpeg_preview(chunk2, tmp_path / "S2.jpg", 90, lambda s: None) == tmp_path / "S2.jpg"


# --- processing --------------------------------------------------------------------

def test_processing_steps_pass_config(tmp_path, fake_metashape):
    cfg = _cfg(tmp_path, set_crs="EPSG:4326", match_downscale=2, depth_downscale=4)
    msgs = []
    doc = processing.open_or_create_project(tmp_path / "p.psx", msgs.append)
    chunk = processing.get_chunk(doc, "S1")
    assert chunk.label == "S1" and doc.saved == [str(tmp_path / "p.psx")]
    processing.apply_crs(chunk, cfg, msgs.append)
    assert chunk.crs == ("CRS", "EPSG:4326")
    processing.add_photos(chunk, ["a.jpg", "b.jpg"], msgs.append)
    processing.add_photos(chunk, ["c.jpg"], msgs.append)            # second call is a no-op
    assert chunk.cameras == ["a.jpg", "b.jpg"]
    processing.align_photos(chunk, cfg, msgs.append)
    processing.build_depth_maps(chunk, cfg, msgs.append)
    processing.build_mesh(chunk, cfg, msgs.append)
    processing.build_orthomosaic(chunk, cfg, msgs.append)
    processing.export_orthomosaic_tiff(chunk, tmp_path / "S1_ortho.tif", cfg, msgs.append)

    names = [c[0] for c in chunk.calls]
    assert names == ["addPhotos", "matchPhotos", "alignCameras", "optimizeCameras", "buildDepthMaps",
                     "buildModel", "buildOrthomosaic", "exportOrthomosaic"]
    kw = {c[0]: c[2] for c in chunk.calls}
    assert kw["matchPhotos"]["downscale"] == 2 and kw["matchPhotos"]["keypoint_limit"] == 60000
    assert kw["buildDepthMaps"] == {"downscale": 4, "filter_mode": "MildFiltering"}
    assert kw["buildModel"]["surface_type"] == "Arbitrary"
    assert kw["exportOrthomosaic"]["world_file"] is False and kw["exportOrthomosaic"]["tiff_big"] is True
    assert (tmp_path / "S1_ortho.tif").exists()


# --- batch end to end ----------------------------------------------------------------

def _library(tmp_path):
    lib = tmp_path / "Ishigaki_2025"
    for survey, n in [("Ishi25_S001_0415_A1", 3), ("Ishi25_S002_0416_A1", 0), ("Ishi26_S001_0101_A1", 2)]:
        (lib / survey / "A").mkdir(parents=True)
        for i in range(n):
            (lib / survey / "A" / f"P{i:04d}.JPG").write_bytes(b"x")
    (lib / "Complete Images").mkdir()
    return lib


def test_batch_run_full_year(tmp_path, fake_metashape):
    from neoreef.metashape import batch
    lib = _library(tmp_path)
    cfg = MetashapeConfig(photo_library=lib, output_base=tmp_path / "out")
    assert batch.run(cfg) == 0
    out = tmp_path / "out"
    assert (out / "Ishi25_S001_0415_A1_ortho.tif").exists()
    assert (out / "Ishi26_S001_0101_A1_ortho.tif").exists()        # 2026 no longer skipped
    assert not (out / "Ishi25_S002_0416_A1_ortho.tif").exists()    # no images -> skipped
    log = (out / "batch_processing.log").read_text(encoding="utf-8")
    assert "Successful : 2 / 3" in log and "[SKIP] Ishi25_S002_0416_A1" in log
    assert "ignored, not a survey folder: Complete Images" in log
    previews = list((lib / "Complete Images").rglob("*.jpg"))
    assert sorted(p.name for p in previews) == ["Ishi25_S001_0415_A1.jpg", "Ishi26_S001_0101_A1.jpg"]
    assert fake_metashape.app.settings.project_absolute_paths is True


def test_batch_run_target_folder_and_failure_handling(tmp_path, fake_metashape, monkeypatch):
    from neoreef.metashape import batch
    lib = _library(tmp_path)
    cfg = MetashapeConfig(photo_library=lib, output_base=tmp_path / "out",
                          target_folder=lib / "Ishi25_S001_0415_A1", continue_on_error=True)
    monkeypatch.setattr(batch.ms, "align_photos", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert batch.run(cfg) == 1
    log = (tmp_path / "out" / "batch_processing.log").read_text(encoding="utf-8")
    assert "[FAIL] Ishi25_S001_0415_A1 - boom" in log and "Successful : 0 / 1" in log

    cfg.continue_on_error = False
    with pytest.raises(RuntimeError):
        batch.run(cfg)


def test_batch_run_bad_library(tmp_path, fake_metashape):
    from neoreef.metashape import batch
    cfg = MetashapeConfig(photo_library=tmp_path / "nope", output_base=tmp_path / "out")
    assert batch.run(cfg) == 1
