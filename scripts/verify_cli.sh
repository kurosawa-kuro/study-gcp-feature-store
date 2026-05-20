#!/usr/bin/env bash
# Feature Store のリソースを CLI から検証する。
#
# 注意: gcloud SDK 563.x には `gcloud ai feature-groups` / `feature-online-stores`
# が存在しない (Feature Store の操作は REST API のみ)。そのため Feature Store 系は
# `gcloud auth print-access-token` + curl で Vertex AI REST API を叩く。
# BigQuery 側は bq CLI が使える。
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-mlops-dev-a}"
REGION="${REGION:-asia-northeast1}"
STORE_ID="${FEATURE_ONLINE_STORE_ID:-mlops_dev_feature_store}"
VIEW_ID="${FEATURE_VIEW_ID:-property_features}"
GROUP_ID="${FEATURE_GROUP_ID:-property_features}"

API="https://${REGION}-aiplatform.googleapis.com/v1"
BASE="projects/${PROJECT_ID}/locations/${REGION}"
TOKEN="$(gcloud auth print-access-token)"

api_get() { curl -sS -H "Authorization: Bearer ${TOKEN}" "${API}/$1"; }
api_post() {
  curl -sS -X POST -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" \
    -d "$2" "${API}/$1"
}

echo "===================================================================="
echo "1. BigQuery — 特徴量の実体 (bq CLI)"
echo "===================================================================="
bq query --use_legacy_sql=false --project_id="${PROJECT_ID}" --format=pretty \
  "SELECT property_id, rent, walk_min, age_years, area_m2, ctr, fav_rate, inquiry_rate
   FROM \`${PROJECT_ID}.feature_mart.property_features_daily\`
   WHERE event_date = CURRENT_DATE('Asia/Tokyo') ORDER BY property_id"
echo
echo "-- online source view (Feature View の materialize 元) --"
bq query --use_legacy_sql=false --project_id="${PROJECT_ID}" --format=pretty \
  "SELECT * FROM \`${PROJECT_ID}.feature_mart.property_features_online_latest\` ORDER BY property_id"

echo
echo "===================================================================="
echo "2. Feature Group + Feature 一覧 (REST)"
echo "===================================================================="
api_get "${BASE}/featureGroups/${GROUP_ID}"
echo
echo "-- Features --"
api_get "${BASE}/featureGroups/${GROUP_ID}/features"

echo
echo "===================================================================="
echo "3. Feature Online Store + Feature View + sync 履歴 (REST)"
echo "===================================================================="
api_get "${BASE}/featureOnlineStores/${STORE_ID}"
echo
echo "-- Feature View --"
api_get "${BASE}/featureOnlineStores/${STORE_ID}/featureViews/${VIEW_ID}"
echo
echo "-- Feature View sync 履歴 (最新5) --"
api_get "${BASE}/featureOnlineStores/${STORE_ID}/featureViews/${VIEW_ID}/featureViewSyncs?pageSize=5"

echo
echo "===================================================================="
echo "4. Online serving — fetchFeatureValues で p001 を引く (REST)"
echo "===================================================================="
DOMAIN="$(api_get "${BASE}/featureOnlineStores/${STORE_ID}" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin).get("dedicatedServingEndpoint",{}).get("publicEndpointDomainName",""))')"
if [[ -n "${DOMAIN}" ]]; then
  curl -sS -X POST -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" \
    -d '{"data_key":{"key":"p001"}}' \
    "https://${DOMAIN}/v1/${BASE}/featureOnlineStores/${STORE_ID}/featureViews/${VIEW_ID}:fetchFeatureValues"
else
  echo "(publicEndpointDomainName 未割当 — Online Store プロビジョニング直後は数分かかる)"
fi

echo
echo "===================================================================="
echo "5. Cloud Run jobs"
echo "===================================================================="
gcloud run jobs list --project="${PROJECT_ID}" --region="${REGION}" \
  --format="table(name, lastExecution.name, lastExecution.completionTime)"
