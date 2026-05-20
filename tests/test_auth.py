"""app.common.auth — access_token のラッパを検証する (google.auth は monkeypatch)。"""

from __future__ import annotations

import pytest

from app.common import auth


class _Creds:
    def __init__(self, token: str | None) -> None:
        self.token = token

    def refresh(self, _request: object) -> None:  # token は refresh 後に立つ想定
        self.token = self.token or "refreshed-token"


def test_access_token_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth.google.auth, "default", lambda **_k: (_Creds("abc"), "proj"))
    assert auth.access_token() == "abc"


def test_access_token_empty_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    creds = _Creds(None)
    creds.refresh = lambda _r: None  # type: ignore[assignment]  # refresh しても token 空のまま
    monkeypatch.setattr(auth.google.auth, "default", lambda **_k: (creds, "proj"))
    with pytest.raises(SystemExit, match="access token"):
        auth.access_token()
