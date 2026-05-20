# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## プロジェクトの目的

不動産物件のサンプルデータを題材に、**BigQuery に蓄積した特徴量を Vertex AI Feature Store に登録し、CLI (`gcloud` / `bq`) と GCP コンソール UI の両方から確認・検証する**学習用プロジェクト。詳細仕様は [README.md](README.md) を参照。

学習対象は「BigQuery = 特徴量データの実体・加工場所」「Feature Store = 特徴量の管理・参照・配信レイヤー」という責務分離を実機で理解すること。実データ確認は BigQuery 側が中心、Feature Store 側は定義・Entity ID・参照経路の管理を担う。

## 現状

**実装済み + 実 GCP 動作検証済み（本体 + アドオン1/2）** (2026-05-20 / mlops-dev-a)。Terraform + Cloud Run jobs + app を実装し、`make deploy → seed-raw → build-features → sync → export(bq/online) → verify` を全 PASS で確認済み。仕様は [docs/01_仕様書.md](docs/01_仕様書.md)、実装の詳細・流用元・検証結果は [docs/02_実装カタログ.md](docs/02_実装カタログ.md)、運用は [docs/03_運用.md](docs/03_運用.md)。

構成:
- `infra/terraform/` — BigQuery (dataset/table/view) + Feature Group/Feature×7 + Online Store(optimized)/Feature View + Artifact Registry + SA/IAM + Cloud Run jobs。Feature Store 系は `google-beta` provider。アドオンで `raw` dataset+4テーブル / GCS export bucket / Cloud Run jobs (seed-raw/build-features/feature-export) を追加。
- `app/` — Cloud Run job アプリ。`main.py` が dispatch table でコマンド分岐。`seed`(固定投入)/`sync`(Feature View sync REST polling)/`seed-raw`+`build-features`(アドオン2: raw→SQL集計)/`export`(アドオン1: CSV/GCS出力)。SQL は `app/sql/build_features.sql`。共通 auth は `app/auth.py`。
- `infra/Dockerfile` — 単一イメージ (Python 3.12 + uv)。
- `Makefile` — `tf-init` / `deploy` / `seed` / `sync` / `seed-raw` / `build-features` / `export` / `verify-cli` / `verify-export` / `check` / `destroy`。

主要コマンド:

```bash
make tf-init        # terraform init
make check          # ruff + terraform fmt -check + validate (GCP に触れない)
make deploy         # AR apply → image build/push → 残り apply
make seed           # Cloud Run job: BigQuery へ固定サンプル投入 (quick 路線)
make sync           # Cloud Run job: Feature View sync + 待機
make verify-cli     # gcloud / bq でリソース確認
make destroy        # 全リソース撤去

# アドオン2 (raw → SQL 集計で特徴量生成。seed の現実路線):
make seed-raw       # raw 4 テーブルへサンプル投入
make build-features # raw → property_features_daily を SQL 生成
# アドオン1 (Feature Store → CSV/GCS 出力):
make export         # 特徴量取得 → CSV → GCS (FETCH_SOURCE 既定 bq、online は --update-env-vars で)
make verify-export  # GCS の出力 CSV を確認
```

アドオン仕様・実装・検証は [docs/01_仕様書.md](docs/01_仕様書.md) §6 / [docs/02_実装カタログ.md](docs/02_実装カタログ.md)。
合成フロー: `make deploy → seed-raw → build-features → sync → export → verify-export → destroy`。

意図的に**採用しない**もの (学習対象外): Cloud Composer / Dataform / Vector Search / KServe / Elasticsearch / skew monitoring。Feature Store 中核 (FeatureGroup/Feature/FeatureView/Online Store/sync) に集中する。

⚠️ **初回 `make sync` は約19〜21分かかる** (実測 2026-05-20)。Optimized Online Store の serving ノード(min2)初期プロビジョニング + 初回 materialize のため。2 回目以降は数分。`app/sync.py` の `TIMEOUT_SEC=1800` はこれを見込んだ値。所要時間の実測内訳は [docs/03_運用.md §5](docs/03_運用.md)。

⚠️ **sync 完了直後は数分間、`fetchFeatureValues` が全 entity 404**（serving ノードへの伝播遅延）。sync 完了 ≠ online 取得可。online 一括取得 (`make export` の `FETCH_SOURCE=online`) は数分おいてから。`app/export.py` は 404 を warn+skip してクラッシュを防ぐ。未 materialize の entity（全特徴量 NULL の行など）も 404 になりうる。

> gcloud SDK 563.x には `gcloud ai feature-*` が無いため Feature Store の CLI 確認は REST API ([scripts/verify_cli.sh](scripts/verify_cli.sh))。`make verify-cli` で実行。
> online モードを使う場合: `gcloud run jobs execute feature-export --update-env-vars "^@^FETCH_SOURCE=online" --wait`（env 値にカンマを含む `ENTITY_KEYS` を渡すときはカスタム区切り `^@^` 必須）。

git: この project 直下で `git init` 済み想定 (`/home/ubuntu/repos` 自体は git repo ではない)。

## アーキテクチャ (データフロー)

仕様上のリソース連鎖は以下。実装時はこの順序で構築・検証する:

```
BigQuery Dataset
  └─ 不動産特徴量テーブル (property_id を Entity ID とする)
       │  ← サンプルレコード投入 / SQL で確認 (実データ検証の中心)
       ▼
Vertex AI Feature Store
  ├─ Feature Group   … BigQuery 特徴量テーブルを登録する単位
  ├─ Feature (列)     … 特徴量カラムを Feature として登録
  ├─ Feature View    … オンラインサービング / 同期のための参照単位
  └─ Online Store    … Feature View の同期先 (オンライン配信)
```

**採用スキーマ** (`property_features_daily`、参照実装準拠): `event_date` (DATE/partition), `feature_timestamp` (TIMESTAMP), `property_id` (STRING / **Entity ID** / clustering), `rent` (INT64), `walk_min` (INT64), `age_years` (INT64), `area_m2` (FLOAT64), `ctr` (FLOAT64), `fav_rate` (FLOAT64), `inquiry_rate` (FLOAT64), `popularity_score` (FLOAT64)。Feature Group に登録する Feature は 7 個 (`rent`/`walk_min`/`age_years`/`area_m2`/`ctr`/`fav_rate`/`inquiry_rate`)。

> README 初版で例示した列 (`area_sqm` / `station_distance_minutes` / `floor` / `has_auto_lock` 等) は採用していない。稼働中の参照実装 [study-gcp-search-mlops-gke](../study-gcp-search-mlops-gke/) との整合を優先し上記スキーマを採用した。

検証は 4 段階: ①BigQuery 側 (dataset/table/投入/SQL) → ②Feature Store 側 (Feature Group/View/Online Store 同期) → ③CLI 検証 (`bq` + Vertex AI REST。`gcloud ai feature-*` は SDK に無い) → ④GCP UI 検証 (コンソールでメタデータ確認)。全段検証済み (2026-05-20)。

## ワークスペース規約 (継承)

このリポジトリは `/home/ubuntu/repos` multi-project workspace 配下。ルートの [/home/ubuntu/repos/CLAUDE.md](../CLAUDE.md) も参照。特に:

- **ドキュメント・コミットメッセージ・PR タイトルは日本語が canonical**。コード内 identifier は英語、ユーザーへの応答は日本語。
- `gcloud *` / `bq *` / `terraform *` 等は workspace の `.claude/settings.json` allowlist に登録済みで、この project でもそのまま使える。
- 実装が増えたら他 project ([study-gcp-search-mlops-gke/](../study-gcp-search-mlops-gke/) 等) の Feature Store 実装を参照可能。同名ファイルが複数 project に存在しうるので path を必ず確認する。
