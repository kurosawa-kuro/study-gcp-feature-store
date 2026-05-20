"""Cloud Run job エントリポイント。引数でコマンドを分岐する。

python -m app.main seed            # BigQuery へ固定サンプル投入 (quick 路線)
python -m app.main sync            # Feature View sync をトリガ + 待機
python -m app.main seed-raw        # アドオン2: raw テーブルへサンプル投入
python -m app.main build-features  # アドオン2: raw → SQL 集計 → property_features_daily
python -m app.main export          # アドオン1: 特徴量を取得し CSV/GCS 出力
"""

from __future__ import annotations

import sys
from collections.abc import Callable

from app.data import build_features, seed, seed_raw
from app.feature_store import export, sync

COMMANDS: dict[str, Callable[[], None]] = {
    "seed": seed.run,
    "sync": sync.run,
    "seed-raw": seed_raw.run,
    "build-features": build_features.run,
    "export": export.run,
}


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(f"usage: python -m app.main <{'|'.join(COMMANDS)}>", file=sys.stderr)
        return 2
    command = argv[1]
    handler = COMMANDS.get(command)
    if handler is None:
        print(
            f"[error] unknown command: {command} (expected {'|'.join(COMMANDS)})",
            file=sys.stderr,
        )
        return 2
    handler()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
