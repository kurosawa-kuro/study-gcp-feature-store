# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## プロジェクトの目的

不動産物件のサンプルデータを題材に、**BigQuery に蓄積した特徴量を Vertex AI Feature Store に登録し、CLI (`gcloud` / `bq`) と GCP コンソール UI の両方から確認・検証する**学習用プロジェクト。詳細仕様は [README.md](README.md) を参照。

学習対象は「BigQuery = 特徴量データの実体・加工場所」「Feature Store = 特徴量の管理・参照・配信レイヤー」という責務分離を実機で理解すること。実データ確認は BigQuery 側が中心、Feature Store 側は定義・Entity ID・参照経路の管理を担う。

## 現状

**実装済み** (2026-05-20)。作業計画書 [docs/作業計画書.md](docs/作業計画書.md) に沿って Terraform + Cloud Run jobs + app を実装。詳細な流用元対応は [docs/参照実装マッピング.md](docs/参照実装マッピング.md)。

構成:
- `infra/terraform/` — BigQuery (dataset/table/view) + Feature Group/Feature×7 + Online Store(optimized)/Feature View + Artifact Registry + SA/IAM + Cloud Run jobs (seed/fv-sync)。Feature Store 系は `google-beta` provider。
- `app/` — Cloud Run job アプリ。`main.py` が `seed`/`sync` を分岐。`seed.py`=BigQuery へサンプル投入、`sync.py`=Feature View sync の REST polling。
- `infra/Dockerfile` — 単一イメージ (Python 3.12 + uv)。
- `Makefile` — `tf-init` / `deploy` (AR apply→build-push→残り apply) / `seed` / `sync` / `verify-cli` / `check` / `destroy`。

主要コマンド:

```bash
make tf-init        # terraform init
make check          # ruff + terraform fmt -check + validate (GCP に触れない)
make deploy         # AR apply → image build/push → 残り apply
make seed           # Cloud Run job: BigQuery へサンプル投入
make sync           # Cloud Run job: Feature View sync + 待機
make verify-cli     # gcloud / bq でリソース確認
make destroy        # 全リソース撤去
```

意図的に**採用しない**もの (学習対象外): Cloud Composer / Dataform / Vector Search / KServe / Elasticsearch / skew monitoring。Feature Store 中核 (FeatureGroup/Feature/FeatureView/Online Store/sync) に集中する。

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

特徴量カラム例 (README より): `property_id` (Entity ID), `rent`, `area_sqm`, `station_distance_minutes`, `building_age_years`, `floor`, `room_count`, `has_auto_lock`, `has_delivery_box`, `popularity_score`, `feature_timestamp`。

検証は 4 段階: ①BigQuery 側 (dataset/table/投入/SQL) → ②Feature Store 側 (Feature Group/View/Online Store 同期) → ③CLI 検証 (`gcloud` / `bq` で一覧・詳細) → ④GCP UI 検証 (コンソールでメタデータ確認)。

## ワークスペース規約 (継承)

このリポジトリは `/home/ubuntu/repos` multi-project workspace 配下。ルートの [/home/ubuntu/repos/CLAUDE.md](../CLAUDE.md) も参照。特に:

- **ドキュメント・コミットメッセージ・PR タイトルは日本語が canonical**。コード内 identifier は英語、ユーザーへの応答は日本語。
- `gcloud *` / `bq *` / `terraform *` 等は workspace の `.claude/settings.json` allowlist に登録済みで、この project でもそのまま使える。
- 実装が増えたら他 project ([study-gcp-search-mlops-gke/](../study-gcp-search-mlops-gke/) 等) の Feature Store 実装を参照可能。同名ファイルが複数 project に存在しうるので path を必ず確認する。
