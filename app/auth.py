"""Cloud Run job SA の access token を取得する共通ヘルパ。

metadata server / ADC のどちらでも `google.auth.default` で解決できる。
sync.py (Feature View sync) と export.py (online fetch) が共有する。
"""

from __future__ import annotations

import google.auth
import google.auth.transport.requests

_SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]


def access_token() -> str:
    creds, _ = google.auth.default(scopes=_SCOPES)
    creds.refresh(google.auth.transport.requests.Request())
    token = creds.token
    if not token:
        raise SystemExit("[error] failed to obtain access token")
    return str(token)
