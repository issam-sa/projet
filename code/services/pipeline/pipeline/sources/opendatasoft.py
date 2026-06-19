from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd
import requests

logger = logging.getLogger("pipeline.ods")

# Endpoint "Explore API v2.1" commun à toutes les plateformes OpenDataSoft.
# Défauts calés sur le jeu "comptages-routiers-permanents" d'opendata.paris.fr :
#   t_1h = horodatage horaire, q = débit (véh/h), k = taux d'occupation (%).
_PAGE_SIZE = 100  # maximum imposé par l'API v2.1


def _records_url(domain: str, dataset: str) -> str:
    domain = domain.strip().rstrip("/")
    if not domain.startswith("http"):
        domain = f"https://{domain}"
    return f"{domain}/api/explore/v2.1/catalog/datasets/{dataset}/records"


def fetch_traffic_records(
    domain: str,
    dataset: str,
    *,
    api_key: str | None = None,
    max_records: int = 2000,
    ts_field: str = "t_1h",
    flow_field: str = "q",
    occ_field: str = "k",
    timeout: int = 30,
) -> pd.DataFrame:
    """Récupère des relevés trafic bruts depuis OpenDataSoft.

    Retourne un DataFrame [ts, volume_veh_h, occupancy] (une ligne par capteur/heure),
    non agrégé. La transformation métier est faite par :func:`aggregate_city_traffic`.
    """
    if not dataset:
        raise ValueError("ODS_DATASET est vide : renseignez un identifiant de jeu de données.")

    url = _records_url(domain, dataset)
    headers = {"Authorization": f"Apikey {api_key}"} if api_key else {}
    rows: list[dict] = []
    offset = 0
    while offset < max_records:
        limit = min(_PAGE_SIZE, max_records - offset)
        params = {
            "select": f"{ts_field},{flow_field},{occ_field}",
            "order_by": f"{ts_field} desc",
            "limit": limit,
            "offset": offset,
        }
        resp = requests.get(url, params=params, headers=headers, timeout=timeout)
        resp.raise_for_status()
        results = resp.json().get("results") or []
        if not results:
            break
        for r in results:
            ts_raw = r.get(ts_field)
            if not ts_raw:
                continue
            rows.append(
                {
                    "ts": _parse_ts(ts_raw),
                    "volume_veh_h": _to_float(r.get(flow_field)),
                    "occupancy": _to_float(r.get(occ_field)),
                }
            )
        if len(results) < limit:
            break
        offset += limit

    logger.info("ODS: %d enregistrements bruts récupérés (dataset=%s)", len(rows), dataset)
    return pd.DataFrame(rows, columns=["ts", "volume_veh_h", "occupancy"])


def aggregate_city_traffic(df: pd.DataFrame) -> pd.DataFrame:
    """Agrège les capteurs en une série horaire « ville » exploitable par le modèle.

    congestion_index = moyenne du taux d'occupation (0..100 %) ramené à [0, 1].
    """
    if df.empty:
        return pd.DataFrame(columns=["ts", "volume_veh_h", "congestion_index"])

    df = df.dropna(subset=["ts"]).copy()
    df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.floor("h")
    grouped = (
        df.groupby("ts", as_index=False)
        .agg(volume_veh_h=("volume_veh_h", "mean"), occupancy=("occupancy", "mean"))
        .sort_values("ts")
    )
    grouped["congestion_index"] = (grouped["occupancy"] / 100.0).clip(0.0, 1.0)
    return grouped[["ts", "volume_veh_h", "congestion_index"]]


def _parse_ts(value: str) -> datetime:
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _to_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
