from __future__ import annotations

from datetime import datetime

import pandas as pd


def parse_ts(v: str) -> datetime:
    return datetime.fromisoformat(v.replace("Z", "+00:00"))


def to_time_df(items: list[dict], ts_col: str = "ts") -> pd.DataFrame:
    """Convertit une liste d'enregistrements API en DataFrame trié par temps."""
    if not items:
        return pd.DataFrame()
    df = pd.DataFrame(items)
    if ts_col in df.columns:
        df[ts_col] = pd.to_datetime(df[ts_col], utc=True)
        df = df.sort_values(ts_col)
    return df


def hourly_mean(df: pd.DataFrame, value_cols: list[str], ts_col: str = "ts") -> pd.DataFrame:
    """Ré-échantillonne une série en moyenne horaire (pour aligner trafic/environnement)."""
    if df.empty or ts_col not in df.columns:
        return pd.DataFrame()
    cols = [c for c in value_cols if c in df.columns]
    if not cols:
        return pd.DataFrame()
    out = (
        df.set_index(ts_col)[cols]
        .resample("1h")
        .mean()
        .dropna(how="all")
        .reset_index()
    )
    return out
