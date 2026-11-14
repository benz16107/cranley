-- Background work inside the database (TimescaleDB jobs and policies).
SET search_path = threshold, public;

-- A StreamingDiskANN graph grown row by row from an empty table answered with recall@10 of 0.0 on 299 rooms; rebuilt,
-- 1.0. Rooms arrive one by one (the vision build, the pgai vectorizer's worker), so a job rebuilds both room-search
-- graphs every hour instead of the app doing it after each build.
CREATE OR REPLACE PROCEDURE threshold.rebuild_room_search(job_id int, config jsonb) LANGUAGE plpgsql AS $$
BEGIN
    REINDEX INDEX threshold.room_text_embedding;
    IF to_regclass('threshold.room_text_description_embedding') IS NOT NULL THEN
        REINDEX INDEX threshold.room_text_description_embedding;
    END IF;
END $$;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM timescaledb_information.jobs WHERE proc_schema = 'threshold' AND proc_name = 'rebuild_room_search') THEN
        PERFORM add_job('threshold.rebuild_room_search', INTERVAL '1 hour');
    END IF;
END $$;

-- The op log copy is for usage analytics during the event; CoStar's terms want derived data gone afterwards, so
-- chunks older than 30 days drop by themselves. ops_hourly keeps the counts (its refresh window is 30 days too).
SELECT add_retention_policy('op_log', INTERVAL '30 days', if_not_exists => true);
