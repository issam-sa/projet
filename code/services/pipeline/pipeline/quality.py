from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd

logger = logging.getLogger("pipeline.quality")

# Plages physiquement plausibles (au-delà -> valeur considérée aberrante).
TRAFFIC_RANGES = {
    "speed_kph": (0.0, 200.0),
    "volume_veh_h": (0.0, 20000.0),
    "congestion_index": (0.0, 1.0),
}
ENV_RANGES = {
    "temperature_c": (-50.0, 60.0),
    "precipitation_mm": (0.0, 500.0),
    "pm2_5": (0.0, 1000.0),
    "no2": (0.0, 1000.0),
    "o3": (0.0, 1000.0),
    "us_aqi": (0.0, 1000.0),
}


@dataclass
class QualityReport:
    table: str
    rows_in: int = 0
    rows_out: int = 0
    duplicates_removed: int = 0
    missing_ts_removed: int = 0
    missing_required_removed: int = 0
    out_of_range_clipped: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "table": self.table,
            "rows_in": self.rows_in,
            "rows_out": self.rows_out,
            "duplicates_removed": self.duplicates_removed,
            "missing_ts_removed": self.missing_ts_removed,
            "missing_required_removed": self.missing_required_removed,
            "out_of_range_clipped": self.out_of_range_clipped,
        }


def _clip_ranges(df: pd.DataFrame, ranges: dict[str, tuple[float, float]], report: QualityReport) -> pd.DataFrame:
    for col, (lo, hi) in ranges.items():
        if col not in df.columns:
            continue
        out_of_range = df[col].notna() & ((df[col] < lo) | (df[col] > hi))
        n = int(out_of_range.sum())
        if n:
            report.out_of_range_clipped[col] = n
            df[col] = df[col].clip(lower=lo, upper=hi)
    return df


def _clean(
    df: pd.DataFrame,
    *,
    table: str,
    unique_cols: list[str],
    required_cols: list[str],
    ranges: dict[str, tuple[float, float]],
) -> tuple[pd.DataFrame, QualityReport]:
    report = QualityReport(table=table, rows_in=len(df))
    if df.empty:
        return df, report

    df = df.copy()

    before = len(df)
    df = df.dropna(subset=["ts"])
    report.missing_ts_removed = before - len(df)

    df = _clip_ranges(df, ranges, report)

    before = len(df)
    df = df.dropna(subset=required_cols)
    report.missing_required_removed = before - len(df)

    before = len(df)
    df = df.drop_duplicates(subset=unique_cols, keep="last")
    report.duplicates_removed = before - len(df)

    report.rows_out = len(df)
    logger.info("Qualité %s: %s", table, report.as_dict())
    return df, report


def clean_traffic(df: pd.DataFrame) -> tuple[pd.DataFrame, QualityReport]:
    return _clean(
        df,
        table="traffic_observations",
        unique_cols=["area_id", "ts", "source"],
        required_cols=["congestion_index"],
        ranges=TRAFFIC_RANGES,
    )


def clean_environment(df: pd.DataFrame) -> tuple[pd.DataFrame, QualityReport]:
    return _clean(
        df,
        table="environment_observations",
        unique_cols=["area_id", "ts", "source"],
        required_cols=[],
        ranges=ENV_RANGES,
    )
