"""build-features job (アドオン2) — raw テーブルから SQL 集計で特徴量テーブルを生成する。

app/sql/build_features.sql (28日window JOIN / SAFE_DIVIDE 欠損補完 / feature_timestamp 付与)
を読み込み、`{project}` を埋めて 1 つの multi-statement query として実行する。
出力先 feature_mart.property_features_daily は Terraform 管理で schema 不変なので、
Feature Group / Feature View には一切影響しない。
"""

from __future__ import annotations

import os
from pathlib import Path

from google.cloud import bigquery

SQL_PATH = Path(__file__).parent / "sql" / "build_features.sql"


def run() -> None:
    project_id = os.environ.get("PROJECT_ID", "")
    if not project_id:
        raise SystemExit("[error] PROJECT_ID is empty")

    sql = SQL_PATH.read_text(encoding="utf-8").format(project=project_id)
    client = bigquery.Client(project=project_id)

    print("==> build-features: raw → feature_mart.property_features_daily")
    client.query(sql).result()
    print("==> build-features complete")
