import threading
import urllib.error
import urllib.request

import pytest

from neoreef.pipeline.stages.serve import make_server, parse_range


@pytest.mark.parametrize("header,size,expected", [
    (None, 100, None),
    ("bytes=0-9", 100, (0, 9)),
    ("bytes=10-", 100, (10, 99)),
    ("bytes=-10", 100, (90, 99)),
    ("bytes=0-500", 100, (0, 99)),
    ("bytes=100-", 100, None),
    ("bytes=5-2", 100, None),
    ("items=0-1", 100, None),
    ("bytes=-", 100, None),
])
def test_parse_range(header, size, expected):
    assert parse_range(header, size) == expected


@pytest.fixture
def served(tmp_path):
    (tmp_path / "data.bin").write_bytes(bytes(range(256)) * 4)   # 1024 bytes
    (tmp_path / "index.html").write_text("<html>hi</html>")
    server = make_server(tmp_path, 0, host="127.0.0.1")
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


# Bypass any HTTP_PROXY in the environment (the lab proxy would otherwise intercept loopback).
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _get(url, **headers):
    req = urllib.request.Request(url, headers=headers)
    with _OPENER.open(req, timeout=5) as r:
        return r.status, dict(r.headers), r.read()


def test_full_get_has_cors_and_accept_ranges(served):
    status, headers, body = _get(served + "/data.bin")
    assert status == 200 and len(body) == 1024
    assert headers["Access-Control-Allow-Origin"] == "*"
    assert headers["Accept-Ranges"] == "bytes"


def test_range_get_returns_206_slice(served):
    status, headers, body = _get(served + "/data.bin", Range="bytes=256-511")
    assert status == 206
    assert headers["Content-Range"] == "bytes 256-511/1024"
    assert headers["Content-Length"] == "256"
    assert body == bytes(range(256))


def test_suffix_range(served):
    status, headers, body = _get(served + "/data.bin", Range="bytes=-4")
    assert status == 206 and body == bytes([252, 253, 254, 255])


def test_unsatisfiable_range_is_416(served):
    with pytest.raises(urllib.error.HTTPError) as ei:
        _get(served + "/data.bin", Range="bytes=5000-")
    assert ei.value.code == 416
    assert ei.value.headers["Content-Range"] == "bytes */1024"


def test_options_preflight(served):
    req = urllib.request.Request(served + "/data.bin", method="OPTIONS")
    with _OPENER.open(req, timeout=5) as r:
        assert r.status == 204
        assert "GET" in r.headers["Access-Control-Allow-Methods"]


def test_directory_index_served(served):
    status, _, body = _get(served + "/")
    assert status == 200 and b"hi" in body
