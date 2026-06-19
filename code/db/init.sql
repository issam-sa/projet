CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS areas (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  lat DOUBLE PRECISION NOT NULL,
  lon DOUBLE PRECISION NOT NULL,
  geom geometry(Point, 4326) GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(lon, lat), 4326)) STORED
);

CREATE TABLE IF NOT EXISTS traffic_observations (
  id BIGSERIAL PRIMARY KEY,
  area_id TEXT NOT NULL REFERENCES areas(id) ON DELETE CASCADE,
  ts TIMESTAMPTZ NOT NULL,
  speed_kph DOUBLE PRECISION,
  volume_veh_h DOUBLE PRECISION,
  congestion_index DOUBLE PRECISION NOT NULL,
  source TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(area_id, ts, source)
);

CREATE INDEX IF NOT EXISTS idx_traffic_area_ts ON traffic_observations(area_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_traffic_ts ON traffic_observations(ts DESC);

CREATE TABLE IF NOT EXISTS environment_observations (
  id BIGSERIAL PRIMARY KEY,
  area_id TEXT NOT NULL REFERENCES areas(id) ON DELETE CASCADE,
  ts TIMESTAMPTZ NOT NULL,
  temperature_c DOUBLE PRECISION,
  precipitation_mm DOUBLE PRECISION,
  pm2_5 DOUBLE PRECISION,
  no2 DOUBLE PRECISION,
  o3 DOUBLE PRECISION,
  us_aqi DOUBLE PRECISION,
  source TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(area_id, ts, source)
);

CREATE INDEX IF NOT EXISTS idx_env_area_ts ON environment_observations(area_id, ts DESC);

CREATE TABLE IF NOT EXISTS crowd_reports (
  id UUID PRIMARY KEY,
  area_id TEXT NOT NULL REFERENCES areas(id) ON DELETE CASCADE,
  ts TIMESTAMPTZ NOT NULL,
  category TEXT NOT NULL,
  severity INTEGER NOT NULL CHECK (severity >= 1 AND severity <= 5),
  description TEXT,
  status TEXT NOT NULL DEFAULT 'open',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_reports_area_ts ON crowd_reports(area_id, ts DESC);

-- Historisation des exécutions ETL (observabilité du pipeline).
CREATE TABLE IF NOT EXISTS etl_runs (
  id UUID PRIMARY KEY,
  mode TEXT NOT NULL,
  status TEXT NOT NULL,
  rows_loaded INTEGER NOT NULL DEFAULT 0,
  started_at TIMESTAMPTZ NOT NULL,
  finished_at TIMESTAMPTZ,
  details JSONB,
  error TEXT
);

CREATE INDEX IF NOT EXISTS idx_etl_runs_started ON etl_runs(started_at DESC);

-- Rétention : exemple de purge des observations de plus de 90 jours.
-- À planifier via cron/pg_cron selon la volumétrie :
--   DELETE FROM traffic_observations WHERE ts < now() - interval '90 days';
--   DELETE FROM environment_observations WHERE ts < now() - interval '90 days';

