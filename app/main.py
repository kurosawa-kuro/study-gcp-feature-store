"""Cloud Run job エントリポイント。引数で seed / sync を分岐する。

python -m app.main seed   # BigQuery へサンプル投入
python -m app.main sync   # Feature View sync をトリガ + 待機
"""

from __future__ import annotations

import sys

from app import seed, sync


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: python -m app.main <seed|sync>", file=sys.stderr)
        return 2
    command = argv[1]
    if command == "seed":
        seed.run()
    elif command == "sync":
        sync.run()
    else:
        print(f"[error] unknown command: {command} (expected seed|sync)", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
