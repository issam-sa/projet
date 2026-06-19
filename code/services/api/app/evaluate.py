from __future__ import annotations

import numpy as np
import pandas as pd

from app.models import get_traffic_series
from app.predictors import MODEL_NAME, fit_hybrid, forecast_steps


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """MAE / RMSE / MAPE robustes (MAPE ignore les valeurs proches de 0)."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    err = y_pred - y_true
    mae = float(np.mean(np.abs(err)))
    rmse = float(np.sqrt(np.mean(err**2)))
    mask = np.abs(y_true) >= 1e-3
    mape = float(np.mean(np.abs(err[mask] / y_true[mask])) * 100.0) if mask.any() else float("nan")
    return {"mae": mae, "rmse": rmse, "mape_pct": mape, "n": int(len(y_true))}


def _infer_step_minutes(index: pd.DatetimeIndex) -> int:
    if len(index) < 2:
        return 5
    deltas = np.diff(index.view("int64")) / 1e9 / 60.0  # minutes
    step = int(round(float(np.median(deltas))))
    return max(1, step)


def _seasonal_naive(values: np.ndarray, test_start: int, period: int) -> np.ndarray:
    """Prévision naïve saisonnière : valeur d'il y a `period` pas (≈ veille)."""
    preds = []
    for i in range(test_start, len(values)):
        ref = i - period
        preds.append(values[ref] if ref >= 0 else values[test_start - 1])
    return np.asarray(preds, dtype=float)


def evaluate_area(area_id: str, test_frac: float = 0.2, lookback_hours: int = 7 * 24) -> dict:
    """Backtest temporel : entraîne sur le début de la série, teste sur la fin.

    Compare le modèle hybride (ARIMA+MLP) à une baseline naïve saisonnière.
    """
    rows = get_traffic_series(area_id, lookback_hours=lookback_hours)
    if not rows:
        raise ValueError(f"No data for area_id={area_id}")

    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.dropna(subset=["congestion_index"]).sort_values("ts").reset_index(drop=True)
    if len(df) < 50:
        raise ValueError("Série trop courte pour une évaluation fiable (min 50 points).")

    index = pd.DatetimeIndex(df["ts"])
    values = df["congestion_index"].to_numpy(dtype=float)
    step_minutes = _infer_step_minutes(index)

    n = len(values)
    n_test = max(1, int(n * test_frac))
    split = n - n_test

    train_series = pd.Series(values[:split], index=index[:split])
    y_true = values[split:]

    # Modèle hybride : on entraîne sur le train et on prévoit n_test pas.
    arima_fit, mlp = fit_hybrid(train_series)
    start = index[split - 1].to_pydatetime()
    horizon_minutes = n_test * step_minutes
    points = forecast_steps(arima_fit, mlp, start, horizon_minutes, step_minutes)
    y_pred = np.asarray([p["congestion_index"] for p in points], dtype=float)[:n_test]

    # Baseline naïve saisonnière (période = 1 jour).
    period = max(1, int(round(24 * 60 / step_minutes)))
    y_naive = _seasonal_naive(values, split, period)[:n_test]

    return {
        "area_id": area_id,
        "step_minutes": step_minutes,
        "train_size": int(split),
        "test_size": int(n_test),
        "models": {
            MODEL_NAME: compute_metrics(y_true, y_pred),
            "seasonal_naive": compute_metrics(y_true, y_naive),
        },
    }
