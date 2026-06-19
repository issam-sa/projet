import pandas as pd

from utils import hourly_mean, parse_ts, to_time_df


def test_parse_ts_z():
    dt = parse_ts("2025-01-01T08:00:00Z")
    assert dt.hour == 8
    assert dt.tzinfo is not None


def test_to_time_df_sorts():
    items = [
        {"ts": "2025-01-01T09:00:00Z", "v": 2},
        {"ts": "2025-01-01T08:00:00Z", "v": 1},
    ]
    df = to_time_df(items)
    assert list(df["v"]) == [1, 2]


def test_to_time_df_empty():
    assert to_time_df([]).empty


def test_hourly_mean():
    items = [
        {"ts": "2025-01-01T08:00:00Z", "congestion_index": 0.2},
        {"ts": "2025-01-01T08:30:00Z", "congestion_index": 0.4},
        {"ts": "2025-01-01T09:00:00Z", "congestion_index": 1.0},
    ]
    df = to_time_df(items)
    out = hourly_mean(df, ["congestion_index"])
    row8 = out[out["ts"] == pd.Timestamp("2025-01-01T08:00:00", tz="UTC")].iloc[0]
    assert abs(row8["congestion_index"] - 0.3) < 1e-9
