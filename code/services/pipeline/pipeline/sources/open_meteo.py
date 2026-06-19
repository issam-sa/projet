from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import requests


def fetch_weather_hourly(lat: float, lon: float, hours: int = 48) -> pd.DataFrame:
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "temperature_2m,precipitation",
        "forecast_days": max(1, int((hours + 23) // 24)),
        "timezone": "UTC",
    }
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    h = data.get("hourly") or {}
    rows = []
    for t, tc, pr in zip(h.get("time") or [], h.get("temperature_2m") or [], h.get("precipitation") or []):
        rows.append(
            {
                "ts": datetime.fromisoformat(t).replace(tzinfo=timezone.utc),
                "temperature_c": float(tc) if tc is not None else None,
                "precipitation_mm": float(pr) if pr is not None else None,
            }
        )
    return pd.DataFrame(rows)


def fetch_air_quality_hourly(lat: float, lon: float, hours: int = 48) -> pd.DataFrame:
    url = "https://air-quality-api.open-meteo.com/v1/air-quality"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "pm2_5,nitrogen_dioxide,ozone,us_aqi",
        "forecast_days": max(1, int((hours + 23) // 24)),
        "timezone": "UTC",
    }
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    h = data.get("hourly") or {}
    rows = []
    for t, p, n, o, a in zip(
        h.get("time") or [],
        h.get("pm2_5") or [],
        h.get("nitrogen_dioxide") or [],
        h.get("ozone") or [],
        h.get("us_aqi") or [],
    ):
        rows.append(
            {
                "ts": datetime.fromisoformat(t).replace(tzinfo=timezone.utc),
                "pm2_5": float(p) if p is not None else None,
                "no2": float(n) if n is not None else None,
                "o3": float(o) if o is not None else None,
                "us_aqi": float(a) if a is not None else None,
            }
        )
    return pd.DataFrame(rows)

