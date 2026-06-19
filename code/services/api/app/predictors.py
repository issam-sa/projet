from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
from sklearn.neural_network import MLPRegressor
from statsmodels.tsa.arima.model import ARIMA

from app.features import make_features
from app.models import get_traffic_series

MODEL_NAME = "arima+mlp"
_CACHE_MAXSIZE = 64
# Cache mémoire {(area_id, last_ts_iso): (arima_fit, mlp, last_ts)}.
# On le gère manuellement pour éviter de relire la série en base juste pour
# calculer la clé de cache (le précédent code la lisait deux fois).
_MODEL_CACHE: OrderedDict[tuple[str, str], tuple[object, object, datetime]] = OrderedDict()


@dataclass
class ForecastResult:
    model_name: str
    points: list[dict]


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _series_from_rows(rows: list[dict]) -> pd.Series:
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.dropna(subset=["congestion_index"]).sort_values("ts")
    return pd.Series(df["congestion_index"].to_numpy(dtype=float), index=pd.DatetimeIndex(df["ts"]))


def fit_hybrid(series: pd.Series) -> tuple[object, object]:
    """Ajuste le modèle hybride : ARIMA sur la série, MLP sur les résidus.

    Le MLP apprend la structure résiduelle à partir de features calendaires
    exogènes (heure, jour, week-end, jour férié, heure de pointe).
    """
    arima_fit = ARIMA(series, order=(2, 0, 2)).fit()
    residuals = arima_fit.resid
    feats = make_features(series.index)
    mlp = MLPRegressor(
        hidden_layer_sizes=(32, 16),
        random_state=42,
        max_iter=400,
        learning_rate_init=0.01,
    )
    mlp.fit(feats.to_numpy(), residuals.to_numpy())
    return arima_fit, mlp


def forecast_steps(
    arima_fit: object,
    mlp: object,
    start: datetime,
    horizon_minutes: int,
    step_minutes: int,
) -> list[dict]:
    steps = max(1, int(horizon_minutes // step_minutes))
    arima_fc = np.asarray(arima_fit.forecast(steps=steps), dtype=float)
    idx = pd.date_range(start=start, periods=steps, freq=f"{step_minutes}min", tz=start.tzinfo)
    feats = make_features(idx)
    residual_fc = np.asarray(mlp.predict(feats.to_numpy()), dtype=float)
    y = np.clip(arima_fc + residual_fc, 0.0, 1.0)
    return [
        {"ts": t.to_pydatetime().isoformat(), "congestion_index": float(v)}
        for t, v in zip(idx, y, strict=False)
    ]


def _get_or_fit_model(area_id: str) -> tuple[object, object, datetime]:
    rows = get_traffic_series(area_id, lookback_hours=7 * 24)
    if not rows:
        raise ValueError(f"No data for area_id={area_id}")
    series = _series_from_rows(rows)
    last_ts = series.index.max().to_pydatetime()
    key = (area_id, last_ts.isoformat())

    cached = _MODEL_CACHE.get(key)
    if cached is not None:
        _MODEL_CACHE.move_to_end(key)
        return cached

    arima_fit, mlp = fit_hybrid(series)
    value = (arima_fit, mlp, last_ts)
    _MODEL_CACHE[key] = value
    _MODEL_CACHE.move_to_end(key)
    while len(_MODEL_CACHE) > _CACHE_MAXSIZE:
        _MODEL_CACHE.popitem(last=False)
    return value


def forecast(area_id: str, horizon_minutes: int = 120, step_minutes: int = 5) -> ForecastResult:
    arima_fit, mlp, fitted_last = _get_or_fit_model(area_id)
    start = max(_utcnow(), fitted_last.replace(tzinfo=timezone.utc) + timedelta(minutes=step_minutes))
    points = forecast_steps(arima_fit, mlp, start, horizon_minutes, step_minutes)
    return ForecastResult(model_name=MODEL_NAME, points=points)
