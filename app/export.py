"""export job (アドオン1) — Feature Store から特徴量を取得し CSV/GCS へ出力する。

取得元は env FETCH_SOURCE で 2 経路:
  - "bq"     : feature_mart.property_features_online_latest を直接 query (offline / 実体)
  - "online" : Online Store の fetchFeatureValues を entity ごとに呼ぶ (serving)

出力: CSV を /tmp に書き、GCS gs://{EXPORT_BUCKET}/{EXPORT_PREFIX}/property_features_YYYYMMDD.csv へ
upload。最後に GCS から読み戻して行数+先頭数件を print し、簡易 downstream 利用を確認する。

モデル学習・Endpoint・推論API は作らない (アドオン1 spec)。
"""

from __future__ import annotations

import csv
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from google.cloud import bigquery, storage

from app.auth import access_token

HEADER = [
    "property_id",
    "rent",
    "walk_min",
    "age_years",
    "area_m2",
    "ctr",
    "fav_rate",
    "inquiry_rate",
]
FEATURE_COLS = HEADER[1:]  # property_id を除いた 7 features


# --------------------------------------------------------------------------
# bq モード
# --------------------------------------------------------------------------
def _fetch_from_bq(project_id: str) -> list[list[Any]]:
    client = bigquery.Client(project=project_id)
    cols = ", ".join(HEADER)
    sql = (
        f"SELECT {cols} FROM `{project_id}.feature_mart.property_features_online_latest` "
        "ORDER BY property_id"
    )
    return [[row[c] for c in HEADER] for row in client.query(sql).result()]


# --------------------------------------------------------------------------
# online モード (Online Store fetchFeatureValues)
# --------------------------------------------------------------------------
def _entity_keys(project_id: str) -> list[str]:
    env_keys = os.environ.get("ENTITY_KEYS", "").strip()
    if env_keys:
        return [k.strip() for k in env_keys.split(",") if k.strip()]
    client = bigquery.Client(project=project_id)
    sql = (
        f"SELECT DISTINCT property_id FROM "
        f"`{project_id}.feature_mart.property_features_online_latest` ORDER BY property_id"
    )
    return [row["property_id"] for row in client.query(sql).result()]


def _request_json(
    url: str, *, method: str, token: str, payload: dict | None = None
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 (Google API のみ)
        return json.loads(resp.read().decode("utf-8") or "{}")


def _scalar(value: dict[str, Any]) -> Any:
    if not value:
        return None
    ((kind, raw),) = value.items()
    return int(raw) if kind == "int64Value" else raw


def _fetch_from_online(
    project_id: str, region: str, store_id: str, view_id: str
) -> list[list[Any]]:
    if not store_id or not view_id:
        raise SystemExit(
            "[error] FEATURE_ONLINE_STORE_ID / FEATURE_VIEW_ID is empty (online モード)"
        )
    token = access_token()
    base = f"projects/{project_id}/locations/{region}"
    api = f"https://{region}-aiplatform.googleapis.com/v1"

    store = _request_json(f"{api}/{base}/featureOnlineStores/{store_id}", method="GET", token=token)
    domain = (store.get("dedicatedServingEndpoint") or {}).get("publicEndpointDomainName", "")
    if not domain:
        raise SystemExit(
            "[error] publicEndpointDomainName 未割当 (Online Store プロビジョニング待ち)"
        )

    fetch_url = (
        f"https://{domain}/v1/{base}/featureOnlineStores/{store_id}"
        f"/featureViews/{view_id}:fetchFeatureValues"
    )
    rows: list[list[Any]] = []
    for key in _entity_keys(project_id):
        resp = _request_json(
            fetch_url, method="POST", token=token, payload={"data_key": {"key": key}}
        )
        features = {
            f["name"]: _scalar(f.get("value") or {})
            for f in (resp.get("keyValues") or {}).get("features", [])
        }
        rows.append([key, *[features.get(c) for c in FEATURE_COLS]])
    return rows


# --------------------------------------------------------------------------
# CSV / GCS
# --------------------------------------------------------------------------
def _write_csv(rows: list[list[Any]], local_path: Path) -> None:
    with local_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(HEADER)
        writer.writerows(rows)


def _downstream_check(bucket: storage.Bucket, blob_name: str) -> None:
    """簡易 downstream 利用確認: GCS から読み戻して行数 + 先頭 3 件を print。"""
    text = bucket.blob(blob_name).download_as_text()
    reader = list(csv.DictReader(text.splitlines()))
    print(f"==> downstream check: {len(reader)} rows from gs://{bucket.name}/{blob_name}")
    for record in reader[:3]:
        print(f"    {record}")


def run() -> None:
    project_id = os.environ.get("PROJECT_ID", "")
    region = os.environ.get("REGION", "asia-northeast1")
    source = os.environ.get("FETCH_SOURCE", "bq").lower()
    bucket_name = os.environ.get("EXPORT_BUCKET", "")
    prefix = os.environ.get("EXPORT_PREFIX", "exports").strip("/")
    if not project_id:
        raise SystemExit("[error] PROJECT_ID is empty")
    if not bucket_name:
        raise SystemExit("[error] EXPORT_BUCKET is empty")

    print(f"==> export: FETCH_SOURCE={source}")
    if source == "bq":
        rows = _fetch_from_bq(project_id)
    elif source == "online":
        rows = _fetch_from_online(
            project_id,
            region,
            os.environ.get("FEATURE_ONLINE_STORE_ID", ""),
            os.environ.get("FEATURE_VIEW_ID", ""),
        )
    else:
        raise SystemExit(f"[error] unknown FETCH_SOURCE: {source} (expected bq|online)")

    if not rows:
        raise SystemExit("[error] 特徴量が 0 件 (seed/build-features/sync を先に実行したか確認)")

    stamp = datetime.now().strftime("%Y%m%d")
    local_path = Path(f"/tmp/property_features_{stamp}.csv")
    _write_csv(rows, local_path)
    print(f"==> wrote {len(rows)} rows to {local_path}")

    blob_name = f"{prefix}/property_features_{stamp}.csv"
    bucket = storage.Client(project=project_id).bucket(bucket_name)
    bucket.blob(blob_name).upload_from_filename(str(local_path))
    print(f"==> uploaded gs://{bucket_name}/{blob_name}")

    _downstream_check(bucket, blob_name)
    print("==> export complete")
