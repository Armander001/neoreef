import logging
from pathlib import Path

import pytest

from neoreef.pipeline.ion.client import IonClient, IonError
from neoreef.pipeline.ion.upload import IonUploadSpec, upload_file

LOG = logging.getLogger("test.ion")
SPEC = IonUploadSpec(name="S1 [coral]", asset_type="IMAGERY", source_type="GEOTIFF")


# --- a scripted fake of the client used by upload_file ---------------------

class FakeClient:
    def __init__(self, existing=None, poll_results=(True,)):
        self.existing = existing or {}        # name -> asset dict
        self.poll_results = list(poll_results)
        self.deleted = []
        self.created = []
        self.uploaded = []
        self.notified = []
        self.next_id = 100

    def find_by_name(self, name):
        return self.existing.get(name)

    def delete_asset(self, asset_id):
        self.deleted.append(asset_id)
        self.existing = {k: v for k, v in self.existing.items() if v["id"] != asset_id}

    def poll_ready(self, asset_id, timeout=600, interval=20.0, log=None):
        return self.poll_results.pop(0) if self.poll_results else False

    def create_asset(self, name, asset_type, source_type, description=""):
        self.created.append(name)
        self.next_id += 1
        return {"assetMetadata": {"id": self.next_id}, "uploadLocation": {"bucket": "b"},
                "onComplete": {"url": "u", "fields": {}}}

    def upload_s3(self, upload_location, file_path, log=None):
        self.uploaded.append(file_path)
        return True

    def notify_complete(self, on_complete):
        self.notified.append(on_complete)


def test_reuses_complete_asset(tmp_path):
    c = FakeClient(existing={"S1 [coral]": {"id": 7, "status": "COMPLETE"}})
    assert upload_file(c, tmp_path / "f.tif", SPEC, LOG) == 7
    assert c.created == [] and c.deleted == []


def test_reuses_legacy_name(tmp_path):
    c = FakeClient(existing={"S1": {"id": 8, "status": "COMPLETE"}})
    assert upload_file(c, tmp_path / "f.tif", SPEC, LOG, legacy_names=("S1",)) == 8
    assert c.created == []


def test_errored_asset_is_deleted_and_reuploaded(tmp_path):
    c = FakeClient(existing={"S1 [coral]": {"id": 9, "status": "DATA_ERROR"}}, poll_results=[True])
    assert upload_file(c, tmp_path / "f.tif", SPEC, LOG) == 101
    assert c.deleted == [9]
    assert c.created == ["S1 [coral]"]
    assert c.uploaded == [tmp_path / "f.tif"] and len(c.notified) == 1


def test_pending_asset_is_waited_for(tmp_path):
    c = FakeClient(existing={"S1 [coral]": {"id": 10, "status": "IN_PROGRESS"}}, poll_results=[True])
    assert upload_file(c, tmp_path / "f.tif", SPEC, LOG) == 10
    assert c.created == []


def test_pending_asset_that_never_completes_is_replaced(tmp_path):
    c = FakeClient(existing={"S1 [coral]": {"id": 11, "status": "AWAITING_FILES"}}, poll_results=[False, True])
    assert upload_file(c, tmp_path / "f.tif", SPEC, LOG) == 101
    assert c.deleted == [11]


def test_fresh_upload_failing_poll_returns_none(tmp_path):
    c = FakeClient(poll_results=[False])
    assert upload_file(c, tmp_path / "f.tif", SPEC, LOG) is None


# --- IonClient against a fake HTTP session ------------------------------------

class Resp:
    def __init__(self, status, payload=None, text=""):
        self.status_code = status
        self.ok = 200 <= status < 300
        self.reason = ""
        self.text = text
        self._payload = payload

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self):
        self.calls = []
        self.get_queue = []

    def get(self, url, headers=None, params=None, timeout=None):
        self.calls.append(("GET", url, params))
        assert headers["Authorization"] == "Bearer tok"
        return self.get_queue.pop(0)

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append(("POST", url, json))
        return Resp(200, {"assetMetadata": {"id": 5}, "uploadLocation": {}, "onComplete": {}})

    def delete(self, url, headers=None, timeout=None):
        self.calls.append(("DELETE", url, None))
        return Resp(204)

    def request(self, method, url, json=None, headers=None, timeout=None):
        self.calls.append((method, url, json))
        return Resp(204)


def test_client_requires_token():
    with pytest.raises(IonError):
        IonClient("")


def test_find_by_name_exact_match_only():
    s = FakeSession()
    s.get_queue.append(Resp(200, {"items": [{"id": 1, "name": "S1 extra"}, {"id": 2, "name": "S1", "status": "COMPLETE"}]}))
    c = IonClient("tok", session=s)
    assert c.find_by_name("S1") == {"id": 2, "name": "S1", "status": "COMPLETE"}
    assert s.calls[0][2] == {"search": "S1"}


def test_poll_ready_sequences():
    s = FakeSession()
    s.get_queue += [Resp(200, {"status": "IN_PROGRESS"}), Resp(200, {"status": "COMPLETE"})]
    slept = []
    c = IonClient("tok", session=s, sleep=slept.append)
    assert c.poll_ready(5, timeout=60, interval=1) is True
    assert slept == [1]

    s.get_queue += [Resp(200, {"status": "ERROR", "errorMessage": "bad"})]
    assert c.poll_ready(5, timeout=60, interval=1) is False


def test_create_asset_raises_on_http_error():
    s = FakeSession()
    s.post = lambda url, json=None, headers=None, timeout=None: Resp(401, text="nope")
    c = IonClient("tok", session=s)
    with pytest.raises(IonError, match="401"):
        c.create_asset("n", "IMAGERY", "GEOTIFF")


def test_notify_complete_uses_method_and_fields():
    s = FakeSession()
    c = IonClient("tok", session=s)
    c.notify_complete({"url": "https://x/done", "method": "POST", "fields": {"a": 1}})
    assert s.calls[-1] == ("POST", "https://x/done", {"a": 1})
