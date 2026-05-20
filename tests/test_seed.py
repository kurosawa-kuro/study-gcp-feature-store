"""app.data.seed — 固定5件投入 SQL の構築を検証する。"""

from __future__ import annotations

import pytest

from app.data import seed
from tests.conftest import FakeBQClient


def test_run_requires_project(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PROJECT_ID", raising=False)
    with pytest.raises(SystemExit):
        seed.run()


def test_run_builds_delete_then_insert(monkeypatch: pytest.MonkeyPatch) -> None:
    rec = FakeBQClient()
    monkeypatch.setattr("app.data.seed.bigquery.Client", lambda *a, **k: rec)
    monkeypatch.setenv("PROJECT_ID", "proj")

    seed.run()

    assert len(rec.queries) == 2
    delete_sql, insert_sql = rec.queries
    assert delete_sql.startswith("DELETE FROM")
    assert 'CURRENT_DATE("Asia/Tokyo")' in delete_sql
    assert "INSERT INTO" in insert_sql
    # 5 物件すべてが VALUES に含まれる
    for pid in ("p001", "p002", "p003", "p004", "p005"):
        assert f'"{pid}"' in insert_sql
    assert insert_sql.count('"p0') == len(seed.PROPERTIES) == 5
    # テーブル参照に project が入る
    assert "`proj.feature_mart.property_features_daily`" in insert_sql
