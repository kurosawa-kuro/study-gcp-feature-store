# GCP Vertex AI Feature Store を学ぶプロジェクト

## 目的

不動産物件のサンプルデータを題材に、BigQuery に蓄積した特徴量を Vertex AI Feature Store に登録し、CLI と GCP コンソール UI の両方から確認・検証する。

## 検証対象

- BigQuery
- Vertex AI Feature Store
- Feature Group
- Feature View
- Online Store
- gcloud CLI
- GCP コンソール UI

## サンプルデータ

不動産物件データを想定する。

例：

- property_id
- rent
- area_sqm
- station_distance_minutes
- building_age_years
- floor
- room_count
- has_auto_lock
- has_delivery_box
- popularity_score
- feature_timestamp

## 検証内容

### 1. BigQuery 側

- Dataset を作成する
- 不動産物件の特徴量テーブルを作成する
- サンプルレコードを投入する
- SQL で特徴量データを確認する

### 2. Vertex AI Feature Store 側

- BigQuery の特徴量テーブルを Feature Group として登録する
- `property_id` を Entity ID として扱う
- 特徴量カラムを Feature として登録する
- Feature View を作成する
- 必要に応じて Online Store への同期を確認する

### 3. CLI 検証

- `gcloud` コマンドで Feature Group / Feature View を確認する
- BigQuery CLI または `bq` コマンドで特徴量テーブルを確認する
- 作成済みリソースの一覧・詳細を確認する

### 4. GCP UI 検証

- BigQuery コンソールでテーブル・データを確認する
- Vertex AI Feature Store 画面で Feature Group / Feature View を確認する
- Feature Store 上で登録済み特徴量のメタデータを確認する

## このプロジェクトで理解すること

- BigQuery は特徴量データの実体・加工場所である
- Feature Store は特徴量の管理・参照・配信レイヤーである
- Feature Group は BigQuery の特徴量テーブルを登録する単位である
- Feature View はオンラインサービングや同期のための参照単位である
- 実データ確認は BigQuery 側が中心である
- Feature Store 側では特徴量の定義・Entity ID・参照経路を管理する