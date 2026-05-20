# Cloud Run job 用イメージ。seed / sync の単一イメージで、job 側 args で分岐する。
FROM python:3.12-slim

# uv (Astral) で依存解決
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# 依存だけ先にインストール (レイヤキャッシュ)
COPY pyproject.toml ./
RUN uv pip install --system --no-cache \
    "google-cloud-bigquery>=3.25" \
    "google-auth>=2.30"

# アプリ本体
COPY app ./app

# 既定は seed。Cloud Run job の args で ["seed"] / ["sync"] を上書きする。
ENTRYPOINT ["python", "-m", "app.main"]
CMD ["seed"]
