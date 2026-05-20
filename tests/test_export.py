"""app.feature_store.export — scalar 変換 / CSV / online 404 skip / env 検証。"""

from __future__ import annotations

import csv
import urllib.error
from pathlib import Path

import pytest

from app.feature_store import export
from tests.conftest import FakeBucket, FakeStorageClient


def test_scalar() -> None:
    assert export._scalar({"int64Value": "120000"}) == 120000
    assert export._scalar({"doubleValue": 0.05}) == 0.05
    assert export._scalar({}) is None


def test_write_csv_roundtrip(tmp_path: Path) -> None:
    rows = [["p001", 120000, 5, 8, 35.0, 0.1, 0.08, 0.02]]
    out = tmp_path / "f.csv"
    export._write_csv(rows, out)
    parsed = list(csv.DictReader(out.read_text(encoding="utf-8").splitlines()))
    assert parsed[0]["property_id"] == "p001"
    assert parsed[0]["ctr"] == "0.1"
    assert list(parsed[0].keys()) == export.HEADER


def test_fetch_from_online_skips_404(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(export, "access_token", lambda: "tok")
    monkeypatch.setenv("ENTITY_KEYS", "p001,p999,p003")

    def fake_req(url: str, *, method: str, token: str, payload=None):
        if method == "GET":
            return {"dedicatedServingEndpoint": {"publicEndpointDomainName": "dom"}}
        key = payload["data_key"]["key"]
        if key == "p999":
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)  # type: ignore[arg-type]
        return {"keyValues": {"features": [{"name": "rent", "value": {"int64Value": "100"}}]}}

    monkeypatch.setattr(export, "_request_json", fake_req)
    rows = export._fetch_from_online("proj", "asia-northeast1", "store", "view")

    ids = [r[0] for r in rows]
    assert ids == ["p001", "p003"]  # p999 は 404 で skip
    assert rows[0][1] == 100  # rent
    assert rows[0][export.HEADER.index("ctr")] is None  # 無い feature は None


def test_fetch_from_online_non_404_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(export, "access_token", lambda: "tok")
    monkeypatch.setenv("ENTITY_KEYS", "p001")

    def fake_req(url: str, *, method: str, token: str, payload=None):
        if method == "GET":
            return {"dedicatedServingEndpoint": {"publicEndpointDomainName": "dom"}}
        raise urllib.error.HTTPError(url, 500, "ISE", {}, None)  # type: ignore[arg-type]

    monkeypatch.setattr(export, "_request_json", fake_req)
    with pytest.raises(urllib.error.HTTPError):
        export._fetch_from_online("proj", "r", "store", "view")


def test_run_env_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PROJECT_ID", raising=False)
    with pytest.raises(SystemExit, match="PROJECT_ID"):
        export.run()
    monkeypatch.setenv("PROJECT_ID", "proj")
    monkeypatch.delenv("EXPORT_BUCKET", raising=False)
    with pytest.raises(SystemExit, match="EXPORT_BUCKET"):
        export.run()


def test_run_unknown_source(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROJECT_ID", "proj")
    monkeypatch.setenv("EXPORT_BUCKET", "bkt")
    monkeypatch.setenv("FETCH_SOURCE", "bogus")
    with pytest.raises(SystemExit, match="unknown FETCH_SOURCE"):
        export.run()


def test_run_bq_mode_uploads_and_downstream(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PROJECT_ID", "proj")
    monkeypatch.setenv("EXPORT_BUCKET", "bkt")
    monkeypatch.setenv("FETCH_SOURCE", "bq")
    rows = [["p001", 120000, 5, 8, 35.0, 0.1, 0.08, 0.02]]
    monkeypatch.setattr(export, "_fetch_from_bq", lambda _p: rows)
    bucket = FakeBucket()
    monkeypatch.setattr("app.feature_store.export.storage.Client", lambda *a, **k: FakeStorageClient(bucket=bucket))

    export.run()

    # GCS に 1 オブジェクト upload され、CSV 内容が読み戻せる
    assert len(bucket.objects) == 1
    body = next(iter(bucket.objects.values()))
    assert "p001" in body
    assert "downstream check: 1 rows" in capsys.readouterr().out


def test_run_empty_rows_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROJECT_ID", "proj")
    monkeypatch.setenv("EXPORT_BUCKET", "bkt")
    monkeypatch.setenv("FETCH_SOURCE", "bq")
    monkeypatch.setattr(export, "_fetch_from_bq", lambda _p: [])
    with pytest.raises(SystemExit, match="0 件"):
        export.run()
