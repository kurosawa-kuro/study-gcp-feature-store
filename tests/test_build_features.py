"""app.data.build_features — SQL テンプレートの読込と project 埋め込みを検証する。"""

from __future__ import annotations

import pytest

from app.data import build_features
from tests.conftest import FakeBQClient


def test_sql_file_exists_and_has_placeholder() -> None:
    assert build_features.SQL_PATH.exists()
    sql = build_features.SQL_PATH.read_text(encoding="utf-8")
    assert "{project}" in sql
    # 期間集計 / 欠損補完 / feature_timestamp のキーが揃っている
    for token in ("SAFE_DIVIDE", "LEFT JOIN", "feature_timestamp", "INTERVAL 28 DAY"):
        assert token in sql


def test_run_substitutes_project_and_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    rec = FakeBQClient()
    monkeypatch.setattr("app.data.build_features.bigquery.Client", lambda *a, **k: rec)
    monkeypatch.setenv("PROJECT_ID", "proj")

    build_features.run()

    assert len(rec.queries) == 1
    sql = rec.queries[0]
    assert "{project}" not in sql  # 置換漏れなし
    assert "`proj.feature_mart.property_features_daily`" in sql
    assert "`proj.raw.search_log`" in sql


def test_run_requires_project(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PROJECT_ID", raising=False)
    with pytest.raises(SystemExit):
        build_features.run()
