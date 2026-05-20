variable "project_id" {
  type        = string
  description = "GCP project ID"
  default     = "mlops-dev-a"
}

variable "region" {
  type        = string
  description = "リージョン (BigQuery / Vertex AI / Cloud Run / Artifact Registry 共通)"
  default     = "asia-northeast1"
}

variable "feature_mart_dataset_id" {
  type        = string
  description = "特徴量テーブルを置く BigQuery dataset"
  default     = "feature_mart"
}

variable "raw_dataset_id" {
  type        = string
  description = "アドオン2: raw / master テーブルを置く BigQuery dataset"
  default     = "raw"
}

variable "feature_online_store_id" {
  type        = string
  description = "Feature Online Store の ID"
  default     = "mlops_dev_feature_store"
}

variable "feature_view_id" {
  type        = string
  description = "Feature View の ID"
  default     = "property_features"
}

variable "ar_repo_id" {
  type        = string
  description = "Cloud Run job イメージ用 Artifact Registry repo"
  default     = "feature-store"
}

variable "image" {
  type        = string
  description = "Cloud Run job が使うイメージ URI (build-push で push したもの)"
  default     = ""
}

variable "enable_feature_online_store" {
  type        = bool
  description = "Online Store + Feature View を作るか。コスト bounding 用に gate。false なら BQ と Feature Group のみ"
  default     = true
}

variable "enable_deletion_protection" {
  type        = bool
  description = "BigQuery table の削除保護。学習用は false で destroy 可能にする"
  default     = false
}
