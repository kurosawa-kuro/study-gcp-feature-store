output "feature_mart_dataset" {
  value       = google_bigquery_dataset.feature_mart.dataset_id
  description = "BigQuery 特徴量 dataset"
}

output "feature_group" {
  value       = google_vertex_ai_feature_group.property_features.name
  description = "Feature Group 名"
}

output "feature_online_store_id" {
  value       = var.enable_feature_online_store ? google_vertex_ai_feature_online_store.property_features[0].name : ""
  description = "Feature Online Store ID (gate off なら空)"
}

output "feature_view_id" {
  value       = var.enable_feature_online_store ? google_vertex_ai_feature_online_store_featureview.property_features[0].name : ""
  description = "Feature View ID (gate off なら空)"
}

output "artifact_registry_repo" {
  value       = google_artifact_registry_repository.repo.name
  description = "Cloud Run job イメージ用 AR repo"
}

output "job_service_account" {
  value       = google_service_account.job_sa.email
  description = "Cloud Run job 実行 SA"
}
