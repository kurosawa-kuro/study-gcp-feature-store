# =========================================================================
# study-gcp-feature-store — 学習用 Feature Store スタック
#   BigQuery (特徴量の実体) → Feature Group / Online Store / Feature View
#   + Cloud Run jobs (seed / fv-sync)
# =========================================================================

locals {
  # Feature Group に登録する特徴量 (property_id は Entity ID なので含めない)。
  # 全て DOUBLE。query-time signal は対象外。
  feature_group_features = [
    { name = "rent", description = "Monthly rent" },
    { name = "walk_min", description = "Walking minutes to nearest station" },
    { name = "age_years", description = "Property age in years" },
    { name = "area_m2", description = "Floor area in square meters" },
    { name = "ctr", description = "Historical click-through rate" },
    { name = "fav_rate", description = "Historical favorite rate" },
    { name = "inquiry_rate", description = "Historical inquiry conversion rate" },
  ]
}

# ---- 必要 API ----
resource "google_project_service" "apis" {
  for_each = toset([
    "aiplatform.googleapis.com",
    "bigquery.googleapis.com",
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false
}

# =========================================================================
# BigQuery — 特徴量の実体・加工場所
# =========================================================================
resource "google_bigquery_dataset" "feature_mart" {
  dataset_id  = var.feature_mart_dataset_id
  location    = var.region
  description = "不動産物件の特徴量マート (Feature Store の offline source)"
  depends_on  = [google_project_service.apis]
}

resource "google_bigquery_table" "property_features_daily" {
  dataset_id          = google_bigquery_dataset.feature_mart.dataset_id
  table_id            = "property_features_daily"
  deletion_protection = var.enable_deletion_protection

  time_partitioning {
    type  = "DAY"
    field = "event_date"
  }
  clustering = ["property_id"]

  schema = jsonencode([
    { name = "event_date", type = "DATE", mode = "REQUIRED" },
    { name = "feature_timestamp", type = "TIMESTAMP", mode = "NULLABLE", description = "Feature Group BigQuery source の feature-time 列" },
    { name = "property_id", type = "STRING", mode = "REQUIRED", description = "Entity ID" },
    { name = "rent", type = "INT64", mode = "NULLABLE" },
    { name = "walk_min", type = "INT64", mode = "NULLABLE" },
    { name = "age_years", type = "INT64", mode = "NULLABLE" },
    { name = "area_m2", type = "FLOAT64", mode = "NULLABLE" },
    { name = "ctr", type = "FLOAT64", mode = "NULLABLE" },
    { name = "fav_rate", type = "FLOAT64", mode = "NULLABLE" },
    { name = "inquiry_rate", type = "FLOAT64", mode = "NULLABLE" },
    { name = "popularity_score", type = "FLOAT64", mode = "NULLABLE" },
  ])
}

# Feature View の online source。当日 1 行/物件に絞り、event_date/feature_timestamp を
# 除外して Feature View の direct BigQuery source 制約に適合させる。
resource "google_bigquery_table" "property_features_online_latest" {
  dataset_id          = google_bigquery_dataset.feature_mart.dataset_id
  table_id            = "property_features_online_latest"
  deletion_protection = var.enable_deletion_protection
  depends_on          = [google_bigquery_table.property_features_daily]

  view {
    use_legacy_sql = false
    query          = <<-SQL
      SELECT
        property_id,
        rent, walk_min, age_years, area_m2,
        ctr, fav_rate, inquiry_rate
      FROM `${var.project_id}.${google_bigquery_dataset.feature_mart.dataset_id}.property_features_daily`
      WHERE event_date = CURRENT_DATE("Asia/Tokyo")
    SQL
  }
}

# =========================================================================
# Vertex AI Feature Group — offline / schema 宣言 (Entity ID = property_id)
# =========================================================================
resource "google_vertex_ai_feature_group" "property_features" {
  provider = google-beta

  name        = "property_features"
  region      = var.region
  description = "feature_mart.property_features_daily を登録した offline Feature Group"

  big_query {
    big_query_source {
      input_uri = "bq://${var.project_id}.${var.feature_mart_dataset_id}.property_features_daily"
    }
    entity_id_columns = ["property_id"]
  }
  depends_on = [google_bigquery_table.property_features_daily]
}

resource "google_vertex_ai_feature_group_feature" "property_features" {
  for_each = { for f in local.feature_group_features : f.name => f }
  provider = google-beta

  name          = each.value.name
  region        = var.region
  feature_group = google_vertex_ai_feature_group.property_features.name
  description   = each.value.description
}

# =========================================================================
# Feature Online Store + Feature View — online serving の接続点
#   enable_feature_online_store = false でこのブロックを外し、コストを止められる。
# =========================================================================
resource "google_vertex_ai_feature_online_store" "property_features" {
  count    = var.enable_feature_online_store ? 1 : 0
  provider = google-beta

  name   = var.feature_online_store_id
  region = var.region

  optimized {}

  dedicated_serving_endpoint {
    private_service_connect_config {
      enable_private_service_connect = false
    }
  }

  # Optimized store は UpdateFeatureOnlineStore を拒否するため drift を無視する。
  lifecycle {
    ignore_changes = [optimized, dedicated_serving_endpoint, labels]
  }
}

resource "google_vertex_ai_feature_online_store_featureview" "property_features" {
  count    = var.enable_feature_online_store ? 1 : 0
  provider = google-beta

  name                 = var.feature_view_id
  region               = var.region
  feature_online_store = google_vertex_ai_feature_online_store.property_features[0].name

  big_query_source {
    uri               = "bq://${var.project_id}.${var.feature_mart_dataset_id}.property_features_online_latest"
    entity_id_columns = ["property_id"]
  }

  # hourly cron + 手動 job sync を併用。
  sync_config {
    cron = "0 * * * *"
  }
  depends_on = [google_bigquery_table.property_features_online_latest]
}

# =========================================================================
# Artifact Registry — Cloud Run job イメージ置き場
#   build-push の前提なので `terraform apply -target=...repo` で先に作る。
# =========================================================================
resource "google_artifact_registry_repository" "repo" {
  location      = var.region
  repository_id = var.ar_repo_id
  format        = "DOCKER"
  description   = "Feature Store 学習用 Cloud Run job イメージ"
  depends_on    = [google_project_service.apis]
}

# =========================================================================
# Service Account + IAM (seed: BigQuery 書込 / fv-sync: aiplatform)
# =========================================================================
resource "google_service_account" "job_sa" {
  account_id   = "feature-store-job"
  display_name = "Feature Store 学習用 Cloud Run job 実行 SA"
}

resource "google_project_iam_member" "job_sa_roles" {
  for_each = toset([
    "roles/bigquery.dataEditor",
    "roles/bigquery.jobUser",
    "roles/aiplatform.user",
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.job_sa.email}"
}

# =========================================================================
# Cloud Run jobs — seed / fv-sync (単一イメージ、args で分岐)
# =========================================================================
resource "google_cloud_run_v2_job" "seed" {
  name     = "seed"
  location = var.region

  # 学習リポなので make destroy で消せるようにする (provider default は true)。
  deletion_protection = false

  template {
    template {
      service_account = google_service_account.job_sa.email
      max_retries     = 1
      timeout         = "600s"
      containers {
        image = var.image
        args  = ["seed"]
        env {
          name  = "PROJECT_ID"
          value = var.project_id
        }
        env {
          name  = "REGION"
          value = var.region
        }
      }
    }
  }
  depends_on = [google_project_iam_member.job_sa_roles]
}

resource "google_cloud_run_v2_job" "fv_sync" {
  name     = "fv-sync"
  location = var.region

  # 学習リポなので make destroy で消せるようにする (provider default は true)。
  deletion_protection = false

  template {
    template {
      service_account = google_service_account.job_sa.email
      max_retries     = 1
      timeout         = "1800s"
      containers {
        image = var.image
        args  = ["sync"]
        env {
          name  = "PROJECT_ID"
          value = var.project_id
        }
        env {
          name  = "REGION"
          value = var.region
        }
        env {
          name  = "FEATURE_ONLINE_STORE_ID"
          value = var.feature_online_store_id
        }
        env {
          name  = "FEATURE_VIEW_ID"
          value = var.feature_view_id
        }
      }
    }
  }
  depends_on = [google_project_iam_member.job_sa_roles]
}
