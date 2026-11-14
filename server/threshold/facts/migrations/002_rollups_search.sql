-- Continuous aggregates, columnstore policies, search indexes and the read-only role.
SET search_path = threshold, public;

-- The current value of every fact, one row per (day, scan, room, field). Real time: facts recorded since the last
-- refresh are folded in at query time, so a rollup includes the building the agent measured a second ago.
CREATE MATERIALIZED VIEW fact_daily WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT time_bucket('1 day', at) AS day, sid, room, field,
       last(value_num, at)     AS value_num,
       last(value_text, at)    AS value_text,
       last(unit, at)          AS unit,
       last(method, at)        AS method,
       last(confidence, at)    AS confidence,
       last(record_value, at)  AS record_value,
       last(building_id, at)   AS building_id,
       last(city, at)          AS city,
       last(zip, at)           AS zip,
       last(kind, at)          AS kind,
       last(property_type, at) AS property_type,
       max(at)                 AS at,
       count(*)                AS observations
FROM fact
GROUP BY day, sid, room, field
WITH NO DATA;
SELECT add_continuous_aggregate_policy('fact_daily', start_offset => INTERVAL '90 days', end_offset => INTERVAL '1 hour',
                                       schedule_interval => INTERVAL '30 minutes');

-- Neighbourhood dashboard: per day, zip, kind and field, how many scans were measured and the spread of values.
-- Built on fact_daily (a hierarchical continuous aggregate); percentile_agg rolls up across days and zips.
CREATE MATERIALIZED VIEW field_zip_daily WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT time_bucket('1 day', day) AS day, city, zip, kind, property_type, field,
       count(*)                  AS scans,
       avg(value_num)            AS mean,
       min(value_num)            AS min,
       max(value_num)            AS max,
       percentile_agg(value_num) AS pct
FROM fact_daily
WHERE room IS NULL AND value_num IS NOT NULL
GROUP BY 1, city, zip, kind, property_type, field
WITH NO DATA;
SELECT add_continuous_aggregate_policy('field_zip_daily', start_offset => INTERVAL '90 days',
                                       end_offset => INTERVAL '1 day', schedule_interval => INTERVAL '1 hour');

-- Flood: rooms wet and wetted floor area per run and water level (5 cm steps), for cross-house comparisons.
CREATE MATERIALIZED VIEW flood_by_level WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT time_bucket('15 minutes', ts) AS bucket, run, sid,
       max(level_m)                         AS level_m,
       count(*) FILTER (WHERE depth_m > 0)  AS rooms_wet,
       count(*)                             AS rooms,
       sum(wet_area_m2)                     AS wet_area_m2,
       max(depth_m)                         AS max_depth_m
FROM flood_depth
GROUP BY bucket, run, sid
WITH NO DATA;

-- Usage analytics: operations per hour, by kind of operation and who made it.
CREATE MATERIALIZED VIEW ops_hourly WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT time_bucket('1 hour', at) AS hour, op, by_whom, tool,
       count(*) AS ops, count(DISTINCT workspace) AS workspaces
FROM op_log
GROUP BY hour, op, by_whom, tool
WITH NO DATA;
SELECT add_continuous_aggregate_policy('ops_hourly', start_offset => INTERVAL '30 days', end_offset => INTERVAL '1 hour',
                                       schedule_interval => INTERVAL '1 hour');

-- Columnstore: each hypertable got a columnstore policy when 001 created it with tsdb.enable_columnstore; chunks
-- older than their chunk interval are compressed by the background job.

-- Search by meaning (StreamingDiskANN with room-type labels for filtered search) and by words (BM25).
CREATE INDEX room_text_embedding ON room_text USING diskann (embedding vector_cosine_ops, labels);
CREATE INDEX room_text_bm25 ON room_text USING bm25 (description) WITH (text_config = 'english');

-- The agent's read-only role: SELECT on this schema only, read-only transactions, a short statement timeout.
DO $$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'threshold_reader') THEN
        CREATE ROLE threshold_reader NOLOGIN;
    END IF;
END $$;
GRANT USAGE ON SCHEMA threshold TO threshold_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA threshold TO threshold_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA threshold GRANT SELECT ON TABLES TO threshold_reader;
ALTER ROLE threshold_reader SET default_transaction_read_only = on;
ALTER ROLE threshold_reader SET statement_timeout = '5s';
