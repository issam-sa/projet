from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timezone
from uuid import uuid4

import pandas as pd
from sqlalchemy import text

from pipeline.db import engine
from pipeline.quality import clean_environment, clean_traffic
from pipeline.sources.open_meteo import fetch_air_quality_hourly, fetch_weather_hourly
from pipeline.sources.opendatasoft import aggregate_city_traffic, fetch_traffic_records
from pipeline.sources.sample import default_areas, generate_environment, generate_traffic

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("pipeline.etl")

ODS_AREA_ID = "paris_ods"


def ensure_schema() -> None:
    """Crée la table d'historisation des exécutions si nécessaire (idempotent)."""
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS etl_runs (
                    id UUID PRIMARY KEY,
                    mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    rows_loaded INTEGER NOT NULL DEFAULT 0,
                    started_at TIMESTAMPTZ NOT NULL,
                    finished_at TIMESTAMPTZ,
                    details JSONB,
                    error TEXT
                )
                """
            )
        )


def _upsert_areas() -> None:
    lat0 = float(os.getenv("DEFAULT_AREA_LAT", "48.8566"))
    lon0 = float(os.getenv("DEFAULT_AREA_LON", "2.3522"))
    areas = default_areas(lat0, lon0)
    with engine.begin() as conn:
        for a in areas:
            conn.execute(
                text(
                    """
                    INSERT INTO areas (id, name, lat, lon)
                    VALUES (:id, :name, :lat, :lon)
                    ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name, lat=EXCLUDED.lat, lon=EXCLUDED.lon
                    """
                ),
                {"id": a.id, "name": a.name, "lat": a.lat, "lon": a.lon},
            )


def _upsert_single_area(area_id: str, name: str) -> None:
    lat0 = float(os.getenv("DEFAULT_AREA_LAT", "48.8566"))
    lon0 = float(os.getenv("DEFAULT_AREA_LON", "2.3522"))
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO areas (id, name, lat, lon)
                VALUES (:id, :name, :lat, :lon)
                ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name
                """
            ),
            {"id": area_id, "name": name, "lat": lat0, "lon": lon0},
        )


def _load_df(df: pd.DataFrame, table: str, unique_cols: list[str]) -> int:
    if df.empty:
        return 0
    cols = list(df.columns)
    placeholders = ", ".join([f":{c}" for c in cols])
    cols_sql = ", ".join(cols)
    conflict = ", ".join(unique_cols)
    updates = ", ".join([f"{c}=EXCLUDED.{c}" for c in cols if c not in unique_cols])
    stmt = text(
        f"""
        INSERT INTO {table} ({cols_sql})
        VALUES ({placeholders})
        ON CONFLICT ({conflict}) DO UPDATE SET {updates}
        """
    )
    rows = df.to_dict(orient="records")
    with engine.begin() as conn:
        conn.execute(stmt, rows)
    return len(rows)


def run_sample(days: int) -> dict:
    _upsert_areas()
    traffic, q_traffic = clean_traffic(generate_traffic(days=days))
    env, q_env = clean_environment(generate_environment(days=days))
    n1 = _load_df(traffic, "traffic_observations", ["area_id", "ts", "source"])
    n2 = _load_df(env, "environment_observations", ["area_id", "ts", "source"])
    return {
        "mode": "sample",
        "traffic_rows": n1,
        "environment_rows": n2,
        "quality": [q_traffic.as_dict(), q_env.as_dict()],
    }


def run_open_meteo(hours: int) -> dict:
    _upsert_areas()
    lat0 = float(os.getenv("DEFAULT_AREA_LAT", "48.8566"))
    lon0 = float(os.getenv("DEFAULT_AREA_LON", "2.3522"))
    areas = default_areas(lat0, lon0)
    frames = []
    for a in areas:
        w = fetch_weather_hourly(a.lat, a.lon, hours=hours)
        aq = fetch_air_quality_hourly(a.lat, a.lon, hours=hours)
        df = w.merge(aq, on="ts", how="outer").sort_values("ts")
        df.insert(0, "area_id", a.id)
        df["source"] = "open-meteo"
        frames.append(df)
    combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    cleaned, q_env = clean_environment(combined)
    total = _load_df(cleaned, "environment_observations", ["area_id", "ts", "source"])
    return {"mode": "open-meteo", "environment_rows": total, "quality": [q_env.as_dict()]}


def run_ods(max_records: int) -> dict:
    domain = os.getenv("ODS_DOMAIN", "opendata.paris.fr")
    dataset = os.getenv("ODS_DATASET", "")
    api_key = os.getenv("ODS_API_KEY") or None
    ts_field = os.getenv("ODS_FIELD_TS", "t_1h")
    flow_field = os.getenv("ODS_FIELD_FLOW", "q")
    occ_field = os.getenv("ODS_FIELD_OCC", "k")

    raw = fetch_traffic_records(
        domain,
        dataset,
        api_key=api_key,
        max_records=max_records,
        ts_field=ts_field,
        flow_field=flow_field,
        occ_field=occ_field,
    )
    agg = aggregate_city_traffic(raw)
    agg.insert(0, "area_id", ODS_AREA_ID)
    agg["source"] = "opendatasoft"

    _upsert_single_area(ODS_AREA_ID, "Paris (capteurs ODS)")
    cleaned, q_traffic = clean_traffic(agg)
    n = _load_df(cleaned, "traffic_observations", ["area_id", "ts", "source"])
    return {"mode": "ods", "traffic_rows": n, "quality": [q_traffic.as_dict()]}


def _record_run(run_id: str, mode: str, started: datetime, status: str, rows: int, details: dict, error: str | None) -> None:
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO etl_runs (id, mode, status, rows_loaded, started_at, finished_at, details, error)
                    VALUES (:id, :mode, :status, :rows, :started, :finished, CAST(:details AS JSONB), :error)
                    """
                ),
                {
                    "id": run_id,
                    "mode": mode,
                    "status": status,
                    "rows": rows,
                    "started": started,
                    "finished": datetime.now(tz=timezone.utc),
                    "details": json.dumps(details),
                    "error": error,
                },
            )
    except Exception:  # noqa: BLE001 - l'historisation ne doit jamais casser l'ETL
        logger.exception("Impossible d'enregistrer l'exécution ETL")


def _count_rows(res: dict) -> int:
    return int(res.get("traffic_rows", 0)) + int(res.get("environment_rows", 0))


def main() -> None:
    p = argparse.ArgumentParser(description="ETL mobilité urbaine")
    p.add_argument("--mode", choices=["sample", "open-meteo", "ods"], default="sample")
    p.add_argument("--days", type=int, default=14)
    p.add_argument("--hours", type=int, default=48)
    p.add_argument("--max-records", type=int, default=2000, help="Limite de relevés ODS")
    args = p.parse_args()

    ensure_schema()
    run_id = str(uuid4())
    started = datetime.now(tz=timezone.utc)
    logger.info("Démarrage ETL mode=%s", args.mode)

    try:
        if args.mode == "sample":
            res = run_sample(days=args.days)
        elif args.mode == "open-meteo":
            res = run_open_meteo(hours=args.hours)
        else:
            res = run_ods(max_records=args.max_records)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Échec ETL")
        _record_run(run_id, args.mode, started, "error", 0, {}, str(exc))
        raise

    res["started_at"] = started.isoformat()
    res["finished_at"] = datetime.now(tz=timezone.utc).isoformat()
    _record_run(run_id, args.mode, started, "success", _count_rows(res), res, None)
    logger.info("ETL terminé: %s", res)
    print(res)


if __name__ == "__main__":
    main()
