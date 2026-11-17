import json

import pytest

from neoreef.pipeline.config import ConfigError, config_from_dict, load_config

BASE = {"OUTPUT_BASE": "/in", "LANDUSE_DIR": "/lu", "CESIUM_OUTPUT_DIR": "/out"}


def test_missing_required_key():
    with pytest.raises(ConfigError, match="LANDUSE_DIR"):
        config_from_dict({"OUTPUT_BASE": "/in", "CESIUM_OUTPUT_DIR": "/out"})


def test_defaults_and_comment_keys_ignored():
    cfg = config_from_dict({**BASE, "_comment": "x", "_comment_paths": "y"})
    assert cfg.use_ion is True
    assert cfg.local_server_port == 8765
    assert cfg.shapefile_fallback_crs == "EPSG:6685"
    assert cfg.continue_on_error is True
    assert cfg.extra_orthos == [] and cfg.known_ion_assets == {}
    assert cfg.has_write_token is False and cfg.has_viewer_token is False


def test_two_tokens():
    cfg = config_from_dict({**BASE, "CESIUM_ION_WRITE_TOKEN": "w" * 30, "CESIUM_ION_VIEWER_TOKEN": "v" * 30})
    assert cfg.ion_write_token == "w" * 30 and cfg.ion_viewer_token == "v" * 30
    assert cfg.has_write_token and cfg.has_viewer_token
    assert not any("deprecated" in w for w in cfg.warnings)


def test_legacy_token_alias_warns_and_never_becomes_viewer_token():
    cfg = config_from_dict({**BASE, "CESIUM_ION_TOKEN": "legacy" * 5})
    assert cfg.ion_write_token == "legacy" * 5
    assert cfg.ion_viewer_token == ""
    assert any("deprecated" in w for w in cfg.warnings)
    assert any("VIEWER_TOKEN" in w for w in cfg.warnings)


def test_placeholder_tokens_are_empty():
    cfg = config_from_dict({**BASE, "CESIUM_ION_WRITE_TOKEN": "YOUR_ION_ACCESS_TOKEN_HERE",
                            "CESIUM_ION_VIEWER_TOKEN": "YOUR_READ_ONLY_TOKEN_HERE"})
    assert not cfg.has_write_token and not cfg.has_viewer_token


def test_no_viewer_warning_when_ion_disabled():
    cfg = config_from_dict({**BASE, "USE_ION": False})
    assert not any("VIEWER_TOKEN" in w for w in cfg.warnings)


def test_server_base_url_stripped():
    cfg = config_from_dict({**BASE, "SERVER_BASE_URL": "http://h/neoreef/"})
    assert cfg.server_base_url == "http://h/neoreef"


def test_positions_default_file_next_to_config(tmp_path):
    cfg_path = tmp_path / "cesium_config.json"
    cfg_path.write_text(json.dumps(BASE), encoding="utf-8")
    (tmp_path / "survey_positions.json").write_text(json.dumps({
        "_comment": "x", "Ishi25_S008_0915_A1": {"lon": 1, "lat": 2, "height": -3}}), encoding="utf-8")
    cfg = load_config(cfg_path)
    assert cfg.survey_positions == {"Ishi25_S008_0915_A1": {"lon": 1, "lat": 2, "height": -3}}
    assert cfg.source_path == cfg_path.resolve()


def test_positions_inline_wins(tmp_path):
    cfg = config_from_dict({**BASE, "SURVEY_POSITIONS": {"A": {"lon": 0, "lat": 0}}})
    assert cfg.survey_positions == {"A": {"lon": 0, "lat": 0}}


def test_positions_file_missing_warns(tmp_path):
    cfg_path = tmp_path / "c.json"
    cfg_path.write_text(json.dumps({**BASE, "SURVEY_POSITIONS_FILE": "nope.json"}), encoding="utf-8")
    cfg = load_config(cfg_path)
    assert cfg.survey_positions == {}
    assert any("nope.json" in w for w in cfg.warnings)


def test_load_config_missing_file(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "missing.json")
