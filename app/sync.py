"""fv-sync job — Vertex AI Feature View の手動 sync をトリガし、完了まで待機する。

Feature View の cron sync (hourly) は seed 前に走ると空のままになるため、seed 直後に
明示 sync して online serving に当日データを反映させる。参照実装
(study-gcp-search-mlops-gke/scripts/domain/gcp/feature_view_sync.py) の REST polling を
移植したが、ID は terraform output ではなく Cloud Run job の env から取得し、認証は
job の Service Account (metadata server) で行う。

REST:
  POST .../featureViews/{view}:sync
  GET  .../featureViews/{view}/featureViewSyncs?pageSize=5  (finalStatus.code==0 まで poll)
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from typing import Any

import google.auth
import google.auth.transport.requests

TIMEOUT_SEC = 1800
POLL_SEC = 15


def _access_token() -> str:
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(google.auth.transport.requests.Request())
    token = creds.token
    if not token:
        raise SystemExit("[error] failed to obtain access token")
    return str(token)


def _request_json(
    url: str, *, method: str = "GET", token: str, payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 (Google API のみ)
        return json.loads(resp.read().decode("utf-8") or "{}")


def _feature_view(project_id: str, region: str, store_id: str, view_id: str) -> str:
    return (
        f"projects/{project_id}/locations/{region}/featureOnlineStores/"
        f"{store_id}/featureViews/{view_id}"
    )


def _list_syncs(
    feature_view: str, *, token: str, region: str, page_size: int = 5
) -> dict[str, Any]:
    parent = urllib.parse.quote(feature_view, safe="/")
    url = (
        f"https://{region}-aiplatform.googleapis.com/v1beta1/"
        f"{parent}/featureViewSyncs?pageSize={page_size}"
    )
    return _request_json(url, token=token)


def _latest_sync_name(feature_view: str, token: str, region: str) -> str:
    payload = _list_syncs(feature_view, token=token, region=region, page_size=1)
    syncs = payload.get("featureViewSyncs", []) or []
    return str(syncs[0].get("name") or "") if syncs else ""


def trigger_and_wait(*, project_id: str, region: str, store_id: str, view_id: str) -> None:
    feature_view = _feature_view(project_id, region, store_id, view_id)
    token = _access_token()
    before_name = _latest_sync_name(feature_view, token, region)

    sync_url = (
        f"https://{region}-aiplatform.googleapis.com/v1beta1/"
        f"{urllib.parse.quote(feature_view, safe='/')}:sync"
    )
    print(f"==> trigger FeatureView sync: {feature_view}")
    _request_json(sync_url, method="POST", token=token, payload={})

    deadline = time.monotonic() + TIMEOUT_SEC
    while time.monotonic() < deadline:
        payload = _list_syncs(feature_view, token=token, region=region)
        syncs = payload.get("featureViewSyncs", []) or []
        if syncs:
            latest = syncs[0]
            name = str(latest.get("name") or "")
            code = int((latest.get("finalStatus") or {}).get("code") or 0)
            end_time = str((latest.get("runTime") or {}).get("endTime") or "")
            if name and name != before_name:
                if code != 0:
                    msg = str((latest.get("finalStatus") or {}).get("message") or "")
                    raise SystemExit(f"[error] FeatureView sync failed code={code} message={msg}")
                if end_time:
                    print(f"==> FeatureView sync complete name={name} end_time={end_time}")
                    return
        print(f"    waiting for sync completion... sleep={POLL_SEC}s")
        time.sleep(POLL_SEC)
    raise SystemExit(f"[error] FeatureView sync timed out after {TIMEOUT_SEC}s")


def run() -> None:
    project_id = os.environ.get("PROJECT_ID", "")
    region = os.environ.get("REGION", "asia-northeast1")
    store_id = os.environ.get("FEATURE_ONLINE_STORE_ID", "")
    view_id = os.environ.get("FEATURE_VIEW_ID", "")
    if not project_id:
        raise SystemExit("[error] PROJECT_ID is empty")
    if not store_id or not view_id:
        raise SystemExit("[error] FEATURE_ONLINE_STORE_ID / FEATURE_VIEW_ID is empty")
    trigger_and_wait(project_id=project_id, region=region, store_id=store_id, view_id=view_id)
