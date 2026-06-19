from __future__ import annotations

from sqlalchemy import text

from app.db import get_session


def list_areas() -> list[dict]:
    with get_session() as s:
        rows = s.execute(text("SELECT id, name, lat, lon FROM areas ORDER BY id")).mappings().all()
        return [dict(r) for r in rows]


def get_latest_traffic(area_id: str) -> dict | None:
    with get_session() as s:
        row = s.execute(
            text(
                """
                SELECT area_id, ts, speed_kph, volume_veh_h, congestion_index, source
                FROM traffic_observations
                WHERE area_id = :area_id
                ORDER BY ts DESC
                LIMIT 1
                """
            ),
            {"area_id": area_id},
        ).mappings().first()
        return dict(row) if row else None


def get_traffic_series(area_id: str, lookback_hours: int = 72) -> list[dict]:
    with get_session() as s:
        rows = s.execute(
            text(
                """
                SELECT ts, congestion_index
                FROM traffic_observations
                WHERE area_id = :area_id
                  AND ts >= now() - (:lookback_hours || ' hours')::interval
                ORDER BY ts ASC
                """
            ),
            {"area_id": area_id, "lookback_hours": lookback_hours},
        ).mappings().all()
        return [dict(r) for r in rows]


def get_latest_traffic_all() -> list[dict]:
    """Dernière observation de trafic par zone, avec coordonnées (pour heatmap/simulation)."""
    with get_session() as s:
        rows = s.execute(
            text(
                """
                SELECT DISTINCT ON (t.area_id)
                       a.id AS area_id, a.name, a.lat, a.lon,
                       t.ts, t.congestion_index, t.speed_kph, t.volume_veh_h
                FROM areas a
                JOIN traffic_observations t ON t.area_id = a.id
                ORDER BY t.area_id, t.ts DESC
                """
            )
        ).mappings().all()
        return [dict(r) for r in rows]


def get_traffic_series_full(area_id: str, lookback_hours: int = 72) -> list[dict]:
    with get_session() as s:
        rows = s.execute(
            text(
                """
                SELECT ts, speed_kph, volume_veh_h, congestion_index, source
                FROM traffic_observations
                WHERE area_id = :area_id
                  AND ts >= now() - (:lookback_hours || ' hours')::interval
                ORDER BY ts ASC
                """
            ),
            {"area_id": area_id, "lookback_hours": lookback_hours},
        ).mappings().all()
        return [dict(r) for r in rows]


def get_environment_latest(area_id: str) -> dict | None:
    with get_session() as s:
        row = s.execute(
            text(
                """
                SELECT area_id, ts, temperature_c, precipitation_mm, pm2_5, no2, o3, us_aqi, source
                FROM environment_observations
                WHERE area_id = :area_id
                ORDER BY ts DESC
                LIMIT 1
                """
            ),
            {"area_id": area_id},
        ).mappings().first()
        return dict(row) if row else None


def get_environment_series(area_id: str, lookback_hours: int = 72) -> list[dict]:
    with get_session() as s:
        rows = s.execute(
            text(
                """
                SELECT ts, temperature_c, precipitation_mm, pm2_5, no2, o3, us_aqi
                FROM environment_observations
                WHERE area_id = :area_id
                  AND ts >= now() - (:lookback_hours || ' hours')::interval
                ORDER BY ts ASC
                """
            ),
            {"area_id": area_id, "lookback_hours": lookback_hours},
        ).mappings().all()
        return [dict(r) for r in rows]


def list_etl_runs(limit: int = 50) -> list[dict]:
    with get_session() as s:
        rows = s.execute(
            text(
                """
                SELECT id, mode, status, rows_loaded, started_at, finished_at, error
                FROM etl_runs
                ORDER BY started_at DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        ).mappings().all()
        return [dict(r) for r in rows]


def count_crowd_reports(area_id: str | None = None) -> int:
    with get_session() as s:
        if area_id:
            row = s.execute(
                text("SELECT count(*) AS n FROM crowd_reports WHERE area_id = :area_id"),
                {"area_id": area_id},
            ).scalar()
        else:
            row = s.execute(text("SELECT count(*) AS n FROM crowd_reports")).scalar()
        return int(row or 0)


def insert_crowd_report(report: dict) -> None:
    with get_session() as s:
        s.execute(
            text(
                """
                INSERT INTO crowd_reports (id, area_id, ts, category, severity, description, status)
                VALUES (:id, :area_id, :ts, :category, :severity, :description, :status)
                """
            ),
            report,
        )
        s.commit()


def list_crowd_reports(area_id: str | None = None, limit: int = 200, offset: int = 0) -> list[dict]:
    with get_session() as s:
        if area_id:
            rows = s.execute(
                text(
                    """
                    SELECT id, area_id, ts, category, severity, description, status
                    FROM crowd_reports
                    WHERE area_id = :area_id
                    ORDER BY ts DESC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                {"area_id": area_id, "limit": limit, "offset": offset},
            ).mappings().all()
        else:
            rows = s.execute(
                text(
                    """
                    SELECT id, area_id, ts, category, severity, description, status
                    FROM crowd_reports
                    ORDER BY ts DESC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                {"limit": limit, "offset": offset},
            ).mappings().all()
        return [dict(r) for r in rows]

