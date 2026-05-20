"""seed job — BigQuery `feature_mart.property_features_daily` へサンプル物件を投入する。

学習用の最小 seed。本番では Dataform 等で特徴量を計算するが、ここでは
Feature Store の登録・同期・参照を学ぶことが目的なので固定サンプルを直接 INSERT する。

冪等性: 当日 (`event_date = CURRENT_DATE`) 分を DELETE してから INSERT するため、
再実行しても当日行は重複しない。テーブル自体は Terraform が作成済みの前提。
"""

from __future__ import annotations

import os

from google.cloud import bigquery

# (property_id, rent, walk_min, age_years, area_m2, ctr, fav_rate, inquiry_rate, popularity_score)
PROPERTIES: list[tuple[str, int, int, int, float, float, float, float, float]] = [
    ("p001", 120000, 5, 8, 35.0, 0.05, 0.10, 0.02, 0.50),
    ("p002", 95000, 3, 12, 22.0, 0.04, 0.08, 0.01, 0.40),
    ("p003", 165000, 7, 5, 50.0, 0.06, 0.12, 0.03, 0.60),
    ("p004", 110000, 4, 15, 25.0, 0.03, 0.07, 0.01, 0.35),
    ("p005", 140000, 6, 10, 42.0, 0.05, 0.11, 0.02, 0.55),
]

TABLE = "feature_mart.property_features_daily"


def run() -> None:
    project_id = os.environ.get("PROJECT_ID", "")
    if not project_id:
        raise SystemExit("[error] PROJECT_ID is empty")

    client = bigquery.Client(project=project_id)
    table = f"`{project_id}.{TABLE}`"

    # 当日分を消してから入れ直す (冪等)。
    print(f"==> delete today's rows from {TABLE}")
    client.query(f'DELETE FROM {table} WHERE event_date = CURRENT_DATE("Asia/Tokyo")').result()

    rows = ",\n      ".join(
        (
            f'(CURRENT_DATE("Asia/Tokyo"), CURRENT_TIMESTAMP(), "{p[0]}", '
            f"{p[1]}, {p[2]}, {p[3]}, {p[4]}, {p[5]}, {p[6]}, {p[7]}, {p[8]})"
        )
        for p in PROPERTIES
    )
    insert_sql = (
        f"INSERT INTO {table}\n"
        "      (event_date, feature_timestamp, property_id, rent, walk_min, age_years,\n"
        "       area_m2, ctr, fav_rate, inquiry_rate, popularity_score)\n"
        f"    VALUES\n      {rows}"
    )
    print(f"==> insert {len(PROPERTIES)} rows into {TABLE}")
    client.query(insert_sql).result()
    print(f"==> seed complete: {len(PROPERTIES)} properties for today")
