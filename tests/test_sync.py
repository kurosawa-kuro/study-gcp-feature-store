"""app.feature_store.sync — REST polling のロジックを検証する (urllib は monkeypatch)。"""

from __future__ import annotations

import pytest

from app.feature_store import sync


def test_feature_view_path() -> None:
    assert sync._feature_view("proj", "asia-northeast1", "store", "view") == (
        "projects/proj/locations/asia-northeast1/featureOnlineStores/store/featureViews/view"
    )


def test_list_syncs_builds_url(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, str] = {}

    def fake_req(url: str, *, token: str, **_kw: object) -> dict[str, object]:
        seen["url"] = url
        return {"featureViewSyncs": []}

    monkeypatch.setattr(sync, "_request_json", fake_req)
    sync._list_syncs("projects/p/locations/r/featureOnlineStores/s/featureViews/v", token="t", region="r")
    assert seen["url"].startswith("https://r-aiplatform.googleapis.com/v1beta1/")
    assert seen["url"].endswith("/featureViewSyncs?pageSize=5")


def _patch_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sync.time, "sleep", lambda *_a: None)


def test_trigger_and_wait_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sync, "_access_token", lambda: "tok")
    _patch_clock(monkeypatch)
    calls = {"n": 0}

    def fake_req(url: str, *, method: str = "GET", token: str = "", payload=None):
        if method == "POST":
            return {}
        calls["n"] += 1
        if calls["n"] == 1:  # before_name 取得 (page_size=1) → 空
            return {"featureViewSyncs": []}
        return {
            "featureViewSyncs": [
                {"name": "sync/123", "finalStatus": {"code": 0}, "runTime": {"endTime": "2026-05-20T00:00:00Z"}}
            ]
        }

    monkeypatch.setattr(sync, "_request_json", fake_req)
    sync.trigger_and_wait(project_id="p", region="r", store_id="s", view_id="v")  # 例外なく完了


def test_trigger_and_wait_failure_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sync, "_access_token", lambda: "tok")
    _patch_clock(monkeypatch)

    def fake_req(url: str, *, method: str = "GET", token: str = "", payload=None):
        if method == "POST":
            return {}
        return {"featureViewSyncs": [{"name": "sync/x", "finalStatus": {"code": 13, "message": "boom"}}]}

    monkeypatch.setattr(sync, "_request_json", fake_req)
    with pytest.raises(SystemExit, match="sync failed"):
        sync.trigger_and_wait(project_id="p", region="r", store_id="s", view_id="v")


def test_trigger_and_wait_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sync, "_access_token", lambda: "tok")
    monkeypatch.setattr(sync.time, "sleep", lambda *_a: None)
    # monotonic を一気に deadline 超えへ進める
    seq = iter([0.0, 0.0, sync.TIMEOUT_SEC + 1])
    monkeypatch.setattr(sync.time, "monotonic", lambda: next(seq))
    monkeypatch.setattr(sync, "_request_json", lambda *a, **k: {"featureViewSyncs": []})
    with pytest.raises(SystemExit, match="timed out"):
        sync.trigger_and_wait(project_id="p", region="r", store_id="s", view_id="v")


def test_run_env_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PROJECT_ID", raising=False)
    with pytest.raises(SystemExit, match="PROJECT_ID"):
        sync.run()
    monkeypatch.setenv("PROJECT_ID", "p")
    monkeypatch.delenv("FEATURE_ONLINE_STORE_ID", raising=False)
    monkeypatch.delenv("FEATURE_VIEW_ID", raising=False)
    with pytest.raises(SystemExit, match="FEATURE_ONLINE_STORE_ID"):
        sync.run()
