"""seed-raw job (アドオン2) — raw dataset の 4 テーブルへサンプルを投入する。

raw テーブル (property_master / search_log / pv_log / favorite_log) は Terraform が
schema 付きで作成済みの前提。ここでは TRUNCATE + INSERT で中身を入れ直す (冪等)。
`CREATE OR REPLACE TABLE` は使わない (Terraform 管理 schema を上書きして drift するため)。

物件ごとに impression / pv / favorite / inquiry の件数を変え、build-features 後の
ctr / fav_rate / inquiry_rate が物件間で差が出るようにする。p006 は行動ログを一切
持たせず、LEFT JOIN で全件出ること + SAFE_DIVIDE が NULL になることを確認できる。
"""

from __future__ import annotations

import os

from google.cloud import bigquery

# (property_id, rent, walk_min, age_years, area_m2, layout, city, ward)
PROPERTY_MASTER = [
    ("p001", 120000, 5, 8, 35.0, "1LDK", "東京都", "新宿区"),
    ("p002", 95000, 3, 12, 22.0, "1R", "東京都", "渋谷区"),
    ("p003", 165000, 7, 5, 50.0, "2LDK", "東京都", "品川区"),
    ("p004", 110000, 4, 15, 25.0, "1K", "東京都", "港区"),
    ("p005", 140000, 6, 10, 42.0, "2DK", "東京都", "目黒区"),
    (
        "p006",
        88000,
        9,
        20,
        28.0,
        "1K",
        "東京都",
        "北区",
    ),  # 行動ログ無し (LEFT JOIN / SAFE_DIVIDE 確認用)
]

# (property_id, impression_count) — search_log
IMPRESSIONS = [("p001", 100), ("p002", 80), ("p003", 120), ("p004", 60), ("p005", 90)]
# (property_id, pv_count) — pv_log (= click 相当, ctr 分子)
PV = [("p001", 10), ("p002", 4), ("p003", 18), ("p004", 3), ("p005", 9)]
# (property_id, favorite_count) — favorite_log action='favorite'
FAVORITE = [("p001", 8), ("p002", 3), ("p003", 14), ("p004", 2), ("p005", 7)]
# (property_id, inquiry_count) — favorite_log action='inquiry'
INQUIRY = [("p001", 2), ("p002", 1), ("p003", 4), ("p004", 0), ("p005", 2)]


def _struct_array(rows: list[tuple[str, int]]) -> str:
    """[STRUCT('p001' AS property_id, 100 AS c), ...] を組み立てる。"""
    items = ", ".join(f"STRUCT('{pid}' AS property_id, {n} AS c)" for pid, n in rows)
    return f"[{items}]"


def run() -> None:
    project_id = os.environ.get("PROJECT_ID", "")
    if not project_id:
        raise SystemExit("[error] PROJECT_ID is empty")
    client = bigquery.Client(project=project_id)

    def q(label: str, sql: str) -> None:
        print(f"==> {label}")
        client.query(sql).result()

    # 1. property_master — 固定マスタ
    master_values = ",\n      ".join(
        f"('{p[0]}', {p[1]}, {p[2]}, {p[3]}, {p[4]}, '{p[5]}', '{p[6]}', '{p[7]}')"
        for p in PROPERTY_MASTER
    )
    q(
        "property_master",
        f"""
        TRUNCATE TABLE `{project_id}.raw.property_master`;
        INSERT INTO `{project_id}.raw.property_master`
          (property_id, rent, walk_min, age_years, area_m2, layout, city, ward)
        VALUES
          {master_values};
        """,
    )

    # 2. search_log — impression を property ごとに GENERATE_ARRAY で展開
    q(
        "search_log",
        f"""
        TRUNCATE TABLE `{project_id}.raw.search_log`;
        INSERT INTO `{project_id}.raw.search_log` (search_id, property_id, query, rank, timestamp)
        SELECT
          CONCAT('s-', prop.property_id, '-', CAST(n AS STRING)) AS search_id,
          prop.property_id,
          'tokyo chintai' AS query,
          CAST(MOD(n, 10) AS INT64) AS rank,
          TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL CAST(MOD(n, 14) AS INT64) DAY) AS timestamp
        FROM UNNEST({_struct_array(IMPRESSIONS)}) AS prop,
             UNNEST(GENERATE_ARRAY(1, prop.c)) AS n;
        """,
    )

    # 3. pv_log — 詳細PV
    q(
        "pv_log",
        f"""
        TRUNCATE TABLE `{project_id}.raw.pv_log`;
        INSERT INTO `{project_id}.raw.pv_log` (property_id, user_id, timestamp)
        SELECT
          prop.property_id,
          CONCAT('u', CAST(MOD(n, 50) AS STRING)) AS user_id,
          TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL CAST(MOD(n, 14) AS INT64) DAY) AS timestamp
        FROM UNNEST({_struct_array(PV)}) AS prop,
             UNNEST(GENERATE_ARRAY(1, prop.c)) AS n;
        """,
    )

    # 4. favorite_log — favorite と inquiry を UNION ALL
    q(
        "favorite_log",
        f"""
        TRUNCATE TABLE `{project_id}.raw.favorite_log`;
        INSERT INTO `{project_id}.raw.favorite_log` (property_id, user_id, action, timestamp)
        SELECT prop.property_id, CONCAT('u', CAST(MOD(n, 50) AS STRING)) AS user_id,
               'favorite' AS action,
               TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL CAST(MOD(n, 14) AS INT64) DAY) AS timestamp
        FROM UNNEST({_struct_array(FAVORITE)}) AS prop,
             UNNEST(GENERATE_ARRAY(1, prop.c)) AS n
        UNION ALL
        SELECT prop.property_id, CONCAT('u', CAST(MOD(n, 50) AS STRING)) AS user_id,
               'inquiry' AS action,
               TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL CAST(MOD(n, 14) AS INT64) DAY) AS timestamp
        FROM UNNEST({_struct_array(INQUIRY)}) AS prop,
             UNNEST(GENERATE_ARRAY(1, prop.c)) AS n;
        """,
    )

    print(f"==> seed-raw complete: {len(PROPERTY_MASTER)} properties (p006 は行動ログ無し)")
