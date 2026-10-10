-- ============================================================================
-- SQL ANALYTICS INTERFACE
-- Each block starts with "-- name: <query_name>" and is executed by
-- etl/analytics.py. Runs on PostgreSQL (and SQLite for the test-suite).
-- ============================================================================

-- name: kpi_overview
-- Headline numbers for the dashboard.
SELECT COUNT(*)                               AS total_products,
       COUNT(DISTINCT category)               AS categories,
       ROUND(AVG(price), 2)                   AS avg_price,
       ROUND(CAST(AVG(rating_rate) AS NUMERIC), 2)             AS avg_rating,
       SUM(rating_count)                      AS total_reviews,
       SUM(CASE WHEN is_highly_rated THEN 1 ELSE 0 END) AS highly_rated_products
FROM transformed_products;

-- name: avg_price_by_category
-- Which categories are the most / least expensive on average?
SELECT category,
       products,
       avg_price,
       avg_rating
FROM vw_category_summary
ORDER BY avg_price DESC;

-- name: top_categories
-- Top categories ranked by customer engagement (total reviews).
SELECT category,
       products,
       total_reviews,
       avg_rating,
       RANK() OVER (ORDER BY total_reviews DESC) AS engagement_rank
FROM vw_category_summary
ORDER BY engagement_rank;

-- name: rating_distribution
-- How are ratings spread? Bucketed to the nearest 0.5 star.
SELECT ROUND(rating_rate * 2) / 2.0 AS rating_bucket,
       COUNT(*)                      AS products
FROM transformed_products
WHERE rating_rate IS NOT NULL
GROUP BY ROUND(rating_rate * 2) / 2.0
ORDER BY rating_bucket;

-- name: price_tier_summary
-- Share of the catalogue per price tier.
SELECT price_tier,
       products,
       avg_rating
FROM vw_price_tier_summary
ORDER BY CASE price_tier WHEN 'budget' THEN 1 WHEN 'mid' THEN 2 ELSE 3 END;

-- name: top_products_by_popularity
-- Window function: best product inside each category.
SELECT category, title, price, rating_rate, rating_count, popularity_score,
       category_rank
FROM (
    SELECT category, title, price, rating_rate, rating_count, popularity_score,
           ROW_NUMBER() OVER (PARTITION BY category
                              ORDER BY popularity_score DESC) AS category_rank
    FROM transformed_products
) ranked
WHERE category_rank = 1
ORDER BY popularity_score DESC;

-- name: price_vs_category_average
-- Window function: how far is each product from its category's average price?
SELECT id, title, category, price,
       ROUND(AVG(price) OVER (PARTITION BY category), 2) AS category_avg_price,
       ROUND(100.0 * (price - AVG(price) OVER (PARTITION BY category))
             / AVG(price) OVER (PARTITION BY category), 1) AS pct_vs_category_avg
FROM transformed_products
ORDER BY pct_vs_category_avg DESC;

-- name: underrated_gems
-- Business question: high rating, many reviews, but priced below category average.
SELECT t.id, t.title, t.category, t.price, t.rating_rate, t.rating_count
FROM transformed_products t
JOIN vw_category_summary c ON c.category = t.category
WHERE t.rating_rate >= 4.0
  AND t.rating_count >= 100
  AND t.price < c.avg_price
ORDER BY t.rating_rate DESC, t.rating_count DESC;

-- name: scatter_price_rating
-- Raw points for the price-vs-rating chart.
SELECT category, title, price, rating_rate, rating_count
FROM transformed_products
WHERE rating_rate IS NOT NULL;

-- name: pipeline_run_history
-- Observability: recent pipeline executions.
SELECT run_id, started_at, finished_at, status,
       rows_extracted, rows_loaded, rows_rejected
FROM pipeline_runs
ORDER BY run_id DESC
LIMIT 10;
