"""共有テストダブル。GCP には一切接続しない。

各 app モジュールは `from google.cloud import bigquery` / `storage` を持つので、
モジュール名前空間の `bigquery.Client` / `storage.Client` を monkeypatch で差し替える。
"""

from __future__ import annotations

from typing import Any


class FakeQueryJob:
    def __init__(self, rows: list[Any] | None = None) -> None:
        self._rows = rows or []

    def result(self) -> list[Any]:
        return self._rows


class FakeBQClient:
    """bigquery.Client の代用。流した SQL を records に貯める。"""

    def __init__(self, *_args: Any, rows: list[Any] | None = None, **_kwargs: Any) -> None:
        self.queries: list[str] = []
        self._rows = rows or []

    def query(self, sql: str, *_args: Any, **_kwargs: Any) -> FakeQueryJob:
        self.queries.append(sql)
        return FakeQueryJob(self._rows)


class FakeBlob:
    def __init__(self, store: dict[str, str], name: str) -> None:
        self._store = store
        self._name = name

    def upload_from_filename(self, path: str) -> None:
        with open(path, encoding="utf-8") as fh:
            self._store[self._name] = fh.read()

    def download_as_text(self) -> str:
        return self._store[self._name]


class FakeBucket:
    def __init__(self, name: str = "bucket") -> None:
        self.name = name
        self.objects: dict[str, str] = {}

    def blob(self, name: str) -> FakeBlob:
        return FakeBlob(self.objects, name)


class FakeStorageClient:
    def __init__(self, *_args: Any, bucket: FakeBucket | None = None, **_kwargs: Any) -> None:
        self._bucket = bucket or FakeBucket()

    def bucket(self, name: str) -> FakeBucket:
        self._bucket.name = name
        return self._bucket
