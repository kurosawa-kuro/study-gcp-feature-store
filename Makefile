# study-gcp-feature-store — Vertex AI Feature Store 学習用
#
# 標準フロー:
#   make tf-init
#   make deploy          # AR repo apply → build-push → 残り apply (image 存在順序を担保)
#   make seed            # Cloud Run job: BigQuery へ固定サンプル投入 (quick 路線)
#   make sync            # Cloud Run job: Feature View sync をトリガ + 待機
#   make verify-cli      # gcloud / bq でリソース確認
#   make destroy         # 全リソース撤去
#
# アドオン2 (raw → SQL 集計で特徴量生成。seed の現実路線):
#   make seed-raw        # raw 4 テーブルへサンプル投入
#   make build-features  # raw → property_features_daily を SQL 生成
#
# アドオン1 (Feature Store → CSV/GCS 出力):
#   make export          # 特徴量取得 → CSV → GCS (FETCH_SOURCE は job env 既定 bq)
#   make verify-export   # GCS の出力を確認

PROJECT_ID ?= mlops-dev-a
REGION     ?= asia-northeast1
AR_REPO    ?= feature-store
IMAGE_TAG  ?= latest
IMAGE      := $(REGION)-docker.pkg.dev/$(PROJECT_ID)/$(AR_REPO)/feature-store-job:$(IMAGE_TAG)

TF_DIR := infra/terraform
TF     := terraform -chdir=$(TF_DIR)
TF_VARS := -var=project_id=$(PROJECT_ID) -var=region=$(REGION) -var=image=$(IMAGE)

.PHONY: help
help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ---- Terraform ----
.PHONY: tf-init
tf-init: ## terraform init
	$(TF) init

.PHONY: tf-validate
tf-validate: ## terraform fmt -check + validate (offline)
	$(TF) fmt -check -recursive
	$(TF) validate

.PHONY: tf-apply-ar
tf-apply-ar: ## Artifact Registry repo だけ先に apply (image push の前提)
	$(TF) apply $(TF_VARS) -target=google_artifact_registry_repository.repo -auto-approve

.PHONY: tf-apply
tf-apply: ## 全リソースを apply
	$(TF) apply $(TF_VARS) -auto-approve

# ---- Container ----
.PHONY: build-push
build-push: ## job image を AR へ build & push
	gcloud auth configure-docker $(REGION)-docker.pkg.dev --quiet
	docker buildx build --platform linux/amd64 -f infra/Dockerfile -t $(IMAGE) --push .

# ---- 一括デプロイ (image 存在順序を担保) ----
.PHONY: deploy
deploy: tf-apply-ar build-push tf-apply ## AR apply → build-push → 残り apply

# ---- Cloud Run jobs 実行 ----
.PHONY: seed
seed: ## seed job 実行 (BigQuery へサンプル投入)
	gcloud run jobs execute seed --project=$(PROJECT_ID) --region=$(REGION) --wait

.PHONY: sync
sync: ## fv-sync job 実行 (Feature View sync + 待機)
	gcloud run jobs execute fv-sync --project=$(PROJECT_ID) --region=$(REGION) --wait

# ---- アドオン2: BQ 内特徴量生成 ----
.PHONY: seed-raw
seed-raw: ## raw 4 テーブルへサンプル投入
	gcloud run jobs execute seed-raw --project=$(PROJECT_ID) --region=$(REGION) --wait

.PHONY: build-features
build-features: ## raw → property_features_daily を SQL 生成
	gcloud run jobs execute build-features --project=$(PROJECT_ID) --region=$(REGION) --wait

# ---- アドオン1: Feature Store → CSV/GCS 出力 ----
.PHONY: export
export: ## 特徴量取得 → CSV → GCS (FETCH_SOURCE=online にするには下記参照)
	gcloud run jobs execute feature-export --project=$(PROJECT_ID) --region=$(REGION) --wait

.PHONY: verify-export
verify-export: ## GCS の出力 CSV を確認
	gcloud storage ls gs://$(PROJECT_ID)-feature-export-$(REGION)/exports/
	gcloud storage cat $$(gcloud storage ls gs://$(PROJECT_ID)-feature-export-$(REGION)/exports/ | tail -1) | head

# ---- 検証 ----
# gcloud SDK 563.x には `gcloud ai feature-*` が無いため、Feature Store 系は
# REST API (curl) で確認する。詳細は scripts/verify_cli.sh。
.PHONY: verify-cli
verify-cli: ## bq + Vertex AI REST でリソース確認
	PROJECT_ID=$(PROJECT_ID) REGION=$(REGION) bash scripts/verify_cli.sh

# ---- ローカル検証 (GCP に触れない) ----
.PHONY: check
check: ## ruff + terraform validate
	uv run ruff check app
	uv run ruff format --check app
	$(TF) fmt -check -recursive
	$(TF) validate

# ---- teardown ----
.PHONY: destroy
destroy: ## 全リソース撤去
	$(TF) destroy $(TF_VARS) -auto-approve
