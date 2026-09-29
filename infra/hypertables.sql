-- Run after `pizza_tracker.cli init` has created the tables:
--   docker compose exec db psql -U pizza -f /docker-entrypoint-initdb.d/hypertables.sql.manual
-- Timescale requires the partition column in every unique index, so swap the PK first.
ALTER TABLE activity_samples DROP CONSTRAINT IF EXISTS activity_samples_pkey;
ALTER TABLE activity_samples ADD PRIMARY KEY (id, ts);
SELECT create_hypertable('activity_samples', 'ts', if_not_exists => TRUE, migrate_data => TRUE);

ALTER TABLE index_readings DROP CONSTRAINT IF EXISTS index_readings_pkey;
ALTER TABLE index_readings ADD PRIMARY KEY (id, ts);
SELECT create_hypertable('index_readings', 'ts', if_not_exists => TRUE, migrate_data => TRUE);

-- Raw samples older than 180 days are only needed as hourly aggregates.
SELECT add_retention_policy('activity_samples', INTERVAL '180 days', if_not_exists => TRUE);
