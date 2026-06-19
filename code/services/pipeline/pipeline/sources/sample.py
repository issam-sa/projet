from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SampleArea:
    id: str
    name: str
    lat: float
    lon: float


def default_areas(lat0: float = 48.8566, lon0: float = 2.3522) -> list[SampleArea]:
    return [
        SampleArea("paris_centre", "Paris Centre", lat0, lon0),
        SampleArea("paris_nord", "Paris Nord", lat0 + 0.04, lon0),
        SampleArea("paris_sud", "Paris Sud", lat0 - 0.04, lon0),
        SampleArea("paris_est", "Paris Est", lat0, lon0 + 0.06),
        SampleArea("paris_ouest", "Paris Ouest", lat0, lon0 - 0.06),
    ]


def generate_traffic(days: int = 14, step_minutes: int = 5, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    end = datetime.now(tz=timezone.utc).replace(second=0, microsecond=0)
    start = end - timedelta(days=days)
    idx = pd.date_range(start=start, end=end, freq=f"{step_minutes}min", tz="UTC")

    rows = []
    for area in default_areas():
        base = rng.uniform(0.2, 0.35)
        rush_amp = rng.uniform(0.35, 0.55)
        noise = rng.normal(0, 0.05, size=len(idx))
        hour = idx.hour.values
        dow = idx.dayofweek.values
        rush = np.exp(-0.5 * ((hour - 8) / 1.5) ** 2) + np.exp(-0.5 * ((hour - 18) / 1.8) ** 2)
        weekend = np.where(dow >= 5, -0.10, 0.0)
        ci = np.clip(base + rush_amp * rush + weekend + noise, 0.0, 1.0)
        speed = np.clip(55 * (1 - ci) + rng.normal(0, 2.5, size=len(idx)), 5, 70)
        volume = np.clip(1200 * (0.3 + ci) + rng.normal(0, 80, size=len(idx)), 50, 2500)
        for t, c, s, v in zip(idx, ci, speed, volume):
            rows.append(
                {
                    "area_id": area.id,
                    "ts": t.to_pydatetime(),
                    "speed_kph": float(s),
                    "volume_veh_h": float(v),
                    "congestion_index": float(c),
                    "source": "sample",
                }
            )
    return pd.DataFrame(rows)


def generate_environment(days: int = 14, step_minutes: int = 60, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    end = datetime.now(tz=timezone.utc).replace(second=0, microsecond=0)
    start = end - timedelta(days=days)
    idx = pd.date_range(start=start, end=end, freq=f"{step_minutes}min", tz="UTC")

    rows = []
    for area in default_areas():
        base_temp = rng.uniform(8, 16)
        temp = base_temp + 7 * np.sin(2 * np.pi * (idx.dayofyear.values / 365.0)) + rng.normal(0, 1.0, size=len(idx))
        pm25 = np.clip(12 + 10 * rng.random(len(idx)) + 10 * (idx.hour.values > 19), 2, 80)
        no2 = np.clip(18 + 12 * rng.random(len(idx)) + 15 * (idx.hour.values < 10), 5, 120)
        o3 = np.clip(25 + 15 * rng.random(len(idx)) + 10 * (idx.hour.values > 12), 5, 160)
        aqi = np.clip(pm25 * 1.2 + no2 * 0.4, 0, 300)
        precipitation = np.clip(rng.exponential(0.2, size=len(idx)) * (rng.random(len(idx)) < 0.15), 0, 12)
        for t, tc, p, n, o, a, pr in zip(idx, temp, pm25, no2, o3, aqi, precipitation):
            rows.append(
                {
                    "area_id": area.id,
                    "ts": t.to_pydatetime(),
                    "temperature_c": float(tc),
                    "precipitation_mm": float(pr),
                    "pm2_5": float(p),
                    "no2": float(n),
                    "o3": float(o),
                    "us_aqi": float(a),
                    "source": "sample",
                }
            )
    return pd.DataFrame(rows)

