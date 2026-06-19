from __future__ import annotations

import logging
import math
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import requests

from app.config import settings

logger = logging.getLogger("app.routing")


class RouteNotFound(Exception):
    """Adresse ou itinéraire introuvable (erreur côté données)."""


class RoutingUnavailable(Exception):
    """Service externe (Nominatim/OSRM) injoignable (erreur réseau)."""


# ───────────────────────────── Réseau ──────────────────────────────────────
def geocode(address: str) -> tuple[float, float]:
    """Convertit une adresse en (lat, lon) via Nominatim (OpenStreetMap)."""
    params = {"q": address, "format": "json", "limit": 1}
    headers = {"User-Agent": settings.routing_user_agent}
    try:
        r = requests.get(settings.nominatim_url, params=params, headers=headers, timeout=20)
        r.raise_for_status()
    except requests.RequestException as e:
        raise RoutingUnavailable(f"Géocodage indisponible: {e}") from e
    data = r.json()
    if not data:
        raise RouteNotFound(f"Adresse introuvable: {address}")
    return float(data[0]["lat"]), float(data[0]["lon"])


def fetch_osrm_routes(
    origin: tuple[float, float],
    destination: tuple[float, float],
    max_alternatives: int = 3,
) -> list[dict]:
    """Calcule un ou plusieurs itinéraires A→B via OSRM.

    Retourne une liste de routes {coordinates, distance_m, duration_s}. OSRM ne
    renvoie pas toujours d'alternatives (selon le trajet) : la liste peut ne
    contenir qu'un seul élément.
    """
    coords = f"{origin[1]},{origin[0]};{destination[1]},{destination[0]}"
    url = f"{settings.osrm_url.rstrip('/')}/route/v1/driving/{coords}"
    params = {
        "overview": "full",
        "geometries": "geojson",
        "steps": "false",
        "alternatives": str(max_alternatives),
    }
    try:
        r = requests.get(url, params=params, timeout=25)
        r.raise_for_status()
    except requests.RequestException as e:
        raise RoutingUnavailable(f"Service de routage indisponible: {e}") from e
    data = r.json()
    if data.get("code") != "Ok" or not data.get("routes"):
        raise RouteNotFound("Aucun itinéraire trouvé entre ces deux points.")
    return [
        {
            "coordinates": rt["geometry"]["coordinates"],  # [[lon, lat], ...]
            "distance_m": float(rt["distance"]),
            "duration_s": float(rt["duration"]),
        }
        for rt in data["routes"]
    ]


# ──────────────────────────── Fonctions pures ──────────────────────────────
def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def nearest_zone(lat: float, lon: float, zones: list[dict]) -> dict | None:
    best, best_d = None, None
    for z in zones:
        d = haversine_m(lat, lon, float(z["lat"]), float(z["lon"]))
        if best_d is None or d < best_d:
            best, best_d = z, d
    return best


def congestion_color(c: float | None) -> list[int]:
    """Vert (fluide) → orange → rouge (saturé). Gris si inconnu."""
    if c is None:
        return [130, 130, 130]
    if c < 0.4:
        return [40, 180, 80]
    if c < 0.7:
        return [240, 170, 40]
    return [220, 50, 50]


def build_route_result(
    coords: list[list[float]],
    distance_m: float,
    duration_s: float,
    zones: list[dict],
    congestion_at: Callable[[str, datetime], float | None],
    depart_in_minutes: int = 0,
    penalty: float = 1.0,
    now: datetime | None = None,
) -> dict:
    """Enrichit un tracé OSRM avec la congestion prédite par zone et un ETA ajusté.

    - coords : liste de [lon, lat] renvoyée par OSRM.
    - congestion_at(zone_id, passage_dt) : congestion prédite (0..1) ou None.
    - penalty : pénalité de temps (durée_segment × (1 + penalty × congestion)).
    """
    now = now or datetime.now(tz=timezone.utc)
    depart = now + timedelta(minutes=depart_in_minutes)
    n = len(coords)
    if n < 2:
        raise RouteNotFound("Tracé d'itinéraire invalide.")

    pts = [(c[1], c[0]) for c in coords]  # (lat, lon)
    seg_d = [haversine_m(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1]) for i in range(n - 1)]
    total_d = sum(seg_d) or 1.0
    seg_dur = [duration_s * (d / total_d) for d in seg_d]  # durée répartie par distance

    # Congestion prédite à chaque point, à l'heure de passage estimée.
    point_zone: list[dict | None] = []
    point_cong: list[float | None] = []
    cum = 0.0
    for i in range(n):
        passage = depart + timedelta(seconds=cum)
        z = nearest_zone(pts[i][0], pts[i][1], zones)
        point_zone.append(z)
        point_cong.append(congestion_at(z["id"], passage) if z else None)
        if i < n - 1:
            cum += seg_dur[i]

    # ETA ajusté : chaque segment pénalisé par la congestion de son point de départ.
    adjusted = 0.0
    for i in range(n - 1):
        c = point_cong[i] if point_cong[i] is not None else 0.0
        adjusted += seg_dur[i] * (1.0 + penalty * c)

    # Regroupement en segments homogènes (même zone) pour l'affichage carte.
    segments: list[dict] = []
    cur: dict | None = None
    for i in range(n - 1):
        z = point_zone[i]
        zid = z["id"] if z else None
        c = point_cong[i]
        if cur is None or cur["zone_id"] != zid:
            if cur:
                segments.append(cur)
            cur = {
                "zone_id": zid,
                "zone_name": z["name"] if z else "Hors zone",
                "congestion": round(c, 3) if c is not None else None,
                "color": congestion_color(c),
                "path": [coords[i], coords[i + 1]],
            }
        else:
            cur["path"].append(coords[i + 1])
    if cur:
        segments.append(cur)

    # Zones distinctes traversées (dans l'ordre).
    zones_traversed: list[dict] = []
    seen: set[str] = set()
    for z, c in zip(point_zone, point_cong, strict=False):
        if z and z["id"] not in seen:
            seen.add(z["id"])
            zones_traversed.append(
                {"zone_id": z["id"], "zone_name": z["name"], "congestion": round(c, 3) if c is not None else None}
            )

    return {
        "distance_km": round(distance_m / 1000.0, 2),
        "duration_min": round(duration_s / 60.0, 1),
        "duration_adjusted_min": round(adjusted / 60.0, 1),
        "delay_min": round((adjusted - duration_s) / 60.0, 1),
        "departure_in_minutes": depart_in_minutes,
        "segments": segments,
        "zones_traversed": zones_traversed,
    }


def make_time_congestion_provider(
    forecast_fn: Callable[[str, int], list[tuple[datetime, float]]],
    latest_fn: Callable[[str], float | None],
    horizon_minutes: int,
) -> Callable[[str, datetime], float | None]:
    """Fabrique un fournisseur de congestion prédite, avec cache par zone.

    forecast_fn(zone_id, horizon) -> liste (datetime, congestion).
    latest_fn(zone_id) -> dernière congestion connue (fallback) ou None.
    """
    cache: dict[str, tuple[str, object]] = {}

    def provider(zone_id: str, passage_dt: datetime) -> float | None:
        if zone_id not in cache:
            series: list[tuple[datetime, float]] = []
            try:
                series = forecast_fn(zone_id, horizon_minutes)
            except Exception:  # noqa: BLE001 - une zone sans données ne casse pas le trajet
                series = []
            if series:
                cache[zone_id] = ("series", series)
            else:
                cache[zone_id] = ("const", latest_fn(zone_id))
        kind, value = cache[zone_id]
        if kind == "const":
            return value  # type: ignore[return-value]
        series = value  # type: ignore[assignment]
        return min(series, key=lambda kv: abs((kv[0] - passage_dt).total_seconds()))[1]

    return provider
