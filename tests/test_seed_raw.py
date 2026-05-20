"""app.data.seed_raw — raw 4 テーブルへの投入と _struct_array を検証する。"""

from __future__ import annotations

import pytest

from app.data import seed_raw
from tests.conftest import FakeBQClient


def test_struct_array() -> None:
    sql = seed_raw._struct_array([("p001", 100), ("p002", 80)])
    assert sql == "[STRUCT('p001' AS property_id, 100 AS c), STRUCT('p002' AS property_id, 80 AS c)]"


def test_sample_counts_consistent() -> None:
    # favorite_log = favorite 34 + inquiry 9 (= 実機検証値)
    assert sum(n for _, n in seed_raw.FAVORITE) == 34
    assert sum(n for _, n in seed_raw.INQUIRY) == 9
    assert sum(n for _, n in seed_raw.IMPRESSIONS) == 450
    assert sum(n for _, n in seed_raw.PV) == 44
    assert len(seed_raw.PROPERTY_MASTER) == 6  # p001..p006


def test_run_truncate_insert_4_tables(monkeypatch: pytest.MonkeyPatch) -> None:
    rec = FakeBQClient()
    monkeypatch.setattr("app.data.seed_raw.bigquery.Client", lambda *a, **k: rec)
    monkeypatch.setenv("PROJECT_ID", "proj")

    seed_raw.run()

    assert len(rec.queries) == 4
    joined = "\n".join(rec.queries)
    for tbl in ("property_master", "search_log", "pv_log", "favorite_log"):
        assert f"`proj.raw.{tbl}`" in joined
    assert joined.count("TRUNCATE TABLE") == 4
    assert joined.count("INSERT INTO") == 4
    assert "GENERATE_ARRAY" in joined
    assert "p006" in joined  # 行動ログ無し物件
    assert "'favorite'" in joined and "'inquiry'" in joined
