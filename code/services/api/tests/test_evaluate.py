import numpy as np
import pandas as pd

from app.evaluate import _infer_step_minutes, _seasonal_naive, compute_metrics


def test_compute_metrics_perfect():
    m = compute_metrics([0.0, 0.5, 1.0], [0.0, 0.5, 1.0])
    assert m["mae"] == 0.0
    assert m["rmse"] == 0.0
    assert m["n"] == 3


def test_compute_metrics_known_values():
    m = compute_metrics([1.0, 1.0], [2.0, 0.0])
    assert abs(m["mae"] - 1.0) < 1e-9
    assert abs(m["rmse"] - 1.0) < 1e-9
    assert abs(m["mape_pct"] - 100.0) < 1e-9


def test_infer_step_minutes():
    idx = pd.date_range("2025-01-01", periods=10, freq="5min", tz="UTC")
    assert _infer_step_minutes(idx) == 5


def test_seasonal_naive():
    values = np.array([0.0, 1.0, 2.0, 3.0])
    preds = _seasonal_naive(values, test_start=2, period=2)
    assert preds.tolist() == [0.0, 1.0]
