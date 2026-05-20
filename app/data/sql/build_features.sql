-- アドオン2: raw テーブル → feature_mart.property_features_daily を生成する。
-- {project} はアプリ側 (app/build_features.py) で format する。
-- 当日分を DELETE してから INSERT する冪等パターン (既存 app/seed.py と同じ)。
-- 出力 schema は Terraform 管理の property_features_daily と完全一致させる。

DELETE FROM `{project}.feature_mart.property_features_daily`
WHERE event_date = CURRENT_DATE("Asia/Tokyo");

INSERT INTO `{project}.feature_mart.property_features_daily`
  (event_date, feature_timestamp, property_id, rent, walk_min, age_years, area_m2,
   ctr, fav_rate, inquiry_rate, popularity_score)
WITH window_bounds AS (
  -- 期間集計: 直近 28 日のログのみ対象
  SELECT TIMESTAMP(DATE_SUB(CURRENT_DATE("Asia/Tokyo"), INTERVAL 28 DAY)) AS window_start
),
impressions AS (
  SELECT property_id, COUNT(*) AS impression_count
  FROM `{project}.raw.search_log`, window_bounds
  WHERE timestamp >= window_bounds.window_start
  GROUP BY property_id
),
pv AS (
  SELECT property_id, COUNT(*) AS pv_count
  FROM `{project}.raw.pv_log`, window_bounds
  WHERE timestamp >= window_bounds.window_start
  GROUP BY property_id
),
acts AS (
  SELECT
    property_id,
    COUNTIF(action = "favorite") AS favorite_count,
    COUNTIF(action = "inquiry")  AS inquiry_count
  FROM `{project}.raw.favorite_log`, window_bounds
  WHERE timestamp >= window_bounds.window_start
  GROUP BY property_id
)
SELECT
  CURRENT_DATE("Asia/Tokyo")            AS event_date,
  TIMESTAMP(CURRENT_DATE("Asia/Tokyo")) AS feature_timestamp,  -- Feature Group の feature-time 列
  m.property_id,
  m.rent,
  m.walk_min,
  m.age_years,
  m.area_m2,
  -- 欠損補完: SAFE_DIVIDE でゼロ除算→NULL、LEFT JOIN で行動ゼロ物件も全件
  SAFE_DIVIDE(pv.pv_count,      i.impression_count) AS ctr,
  SAFE_DIVIDE(a.favorite_count, i.impression_count) AS fav_rate,
  SAFE_DIVIDE(a.inquiry_count,  i.impression_count) AS inquiry_rate,
  ( 0.4 * COALESCE(SAFE_DIVIDE(pv.pv_count,      i.impression_count), 0)
  + 0.2 * COALESCE(SAFE_DIVIDE(a.favorite_count, i.impression_count), 0)
  + 0.2 * COALESCE(SAFE_DIVIDE(a.inquiry_count,  i.impression_count), 0)
  )                                                  AS popularity_score
FROM `{project}.raw.property_master` m
LEFT JOIN impressions i USING (property_id)
LEFT JOIN pv            USING (property_id)
LEFT JOIN acts a        USING (property_id);
