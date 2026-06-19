from datetime import datetime, timezone

import pandas as pd

from pipeline.quality import clean_environment, clean_traffic


def _ts(h):
    return datetime(2025, 1, 1, h, 0, tzinfo=timezone.utc)


def test_clean_traffic_dedup_keeps_last():
    df = pd.DataFrame(
        [
            {"area_id": "a", "ts": _ts(0), "congestion_index": 0.2, "source": "s"},
            {"area_id": "a", "ts": _ts(0), "congestion_index": 0.9, "source": "s"},
        ]
    )
    out, report = clean_traffic(df)
    assert len(out) == 1
    assert report.duplicates_removed == 1
    assert out.iloc[0]["congestion_index"] == 0.9


def test_clean_traffic_clips_out_of_range():
    df = pd.DataFrame(
        [
            {"area_id": "a", "ts": _ts(0), "congestion_index": 1.8, "source": "s"},
            {"area_id": "a", "ts": _ts(1), "congestion_index": -0.5, "source": "s"},
        ]
    )
    out, report = clean_traffic(df)
    assert out["congestion_index"].between(0.0, 1.0).all()
    assert report.out_of_range_clipped.get("congestion_index") == 2


def test_clean_traffic_drops_missing_required():
    df = pd.DataFrame(
        [
            {"area_id": "a", "ts": _ts(0), "congestion_index": None, "source": "s"},
            {"area_id": "a", "ts": _ts(1), "congestion_index": 0.3, "source": "s"},
        ]
    )
    out, report = clean_traffic(df)
    assert len(out) == 1
    assert report.missing_required_removed == 1


def test_clean_environment_empty():
    out, report = clean_environment(pd.DataFrame())
    assert out.empty
    assert report.rows_in == 0
