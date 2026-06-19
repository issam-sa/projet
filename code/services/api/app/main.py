from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from functools import wraps
from uuid import uuid4

from flask import Flask, g, jsonify, request
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.exceptions import HTTPException

from app.config import settings
from app.evaluate import evaluate_area
from app.logging_config import configure_logging
from app.metrics import init_metrics
from app.models import (
    count_crowd_reports,
    get_environment_latest,
    get_environment_series,
    get_latest_traffic,
    get_latest_traffic_all,
    get_traffic_series_full,
    insert_crowd_report,
    list_areas,
    list_crowd_reports,
    list_etl_runs,
)
from app.predictors import forecast
from app.recommendations import recommend
from app.routing import (
    RouteNotFound,
    RoutingUnavailable,
    build_route_result,
    fetch_osrm_routes,
    geocode,
    make_time_congestion_provider,
)
from app.schemas import CrowdReportIn, RouteIn, ValidationError
from app.simulation import simulate_zones

logger = logging.getLogger("app.api")


def _error(message: str, code: int, details: object | None = None):
    body: dict = {"error": message, "code": code}
    if details is not None:
        body["details"] = details
    return jsonify(body), code


def _require_area_id() -> str:
    area_id = request.args.get("area_id", type=str)
    if not area_id:
        raise _ApiError("Missing area_id", 400)
    return area_id


def _bounded_int(name: str, default: int, lo: int, hi: int) -> int:
    val = request.args.get(name, default=default, type=int)
    if val is None:
        val = default
    return max(lo, min(hi, val))


class _ApiError(Exception):
    def __init__(self, message: str, code: int) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


def create_app() -> Flask:
    configure_logging(settings.log_level)
    app = Flask(__name__)

    CORS(app, origins=settings.cors_origins)
    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=[settings.rate_limit_default],
        storage_uri="memory://",
    )
    init_metrics(app)

    # ---- Journalisation des requêtes ----
    @app.before_request
    def _log_start() -> None:
        g._t0 = time.perf_counter()

    @app.after_request
    def _log_end(response):
        latency_ms = round((time.perf_counter() - getattr(g, "_t0", time.perf_counter())) * 1000, 2)
        logger.info(
            "request",
            extra={
                "method": request.method,
                "path": request.path,
                "status": response.status_code,
                "latency_ms": latency_ms,
                "remote_addr": get_remote_address(),
            },
        )
        return response

    # ---- Gestion uniforme des erreurs ----
    @app.errorhandler(_ApiError)
    def _handle_api_error(exc: _ApiError):
        return _error(exc.message, exc.code)

    @app.errorhandler(ValidationError)
    def _handle_validation(exc: ValidationError):
        details = [
            {
                "field": ".".join(str(p) for p in e.get("loc", ())),
                "message": e.get("msg", ""),
                "type": e.get("type", ""),
            }
            for e in exc.errors()
        ]
        return _error("Validation échouée", 400, details=details)

    @app.errorhandler(HTTPException)
    def _handle_http(exc: HTTPException):
        return _error(exc.description or exc.name, exc.code or 500)

    @app.errorhandler(Exception)
    def _handle_unexpected(exc: Exception):
        logger.exception("Erreur non gérée")
        return _error("Erreur interne", 500)

    def require_api_key(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if settings.api_key and request.headers.get("X-API-Key") != settings.api_key:
                raise _ApiError("Clé API invalide ou manquante", 401)
            return fn(*args, **kwargs)

        return wrapper

    # ---- Santé ----
    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "ts": datetime.now(tz=timezone.utc).isoformat()})

    # ---- Zones ----
    @app.get("/api/v1/areas")
    def areas():
        return jsonify({"items": list_areas()})

    # ---- Trafic ----
    @app.get("/api/v1/traffic/latest")
    def traffic_latest():
        area_id = _require_area_id()
        row = get_latest_traffic(area_id)
        if not row:
            raise _ApiError("Not found", 404)
        return jsonify(row)

    @app.get("/api/v1/traffic/series")
    def traffic_series():
        area_id = _require_area_id()
        hours = _bounded_int("hours", default=72, lo=1, hi=24 * 30)
        return jsonify({"area_id": area_id, "items": get_traffic_series_full(area_id, lookback_hours=hours)})

    @app.get("/api/v1/traffic/overview")
    def traffic_overview():
        return jsonify({"items": get_latest_traffic_all()})

    @app.get("/api/v1/simulation")
    def simulation():
        reduction = _bounded_int("reduction_pct", default=10, lo=0, hi=90)
        zones = get_latest_traffic_all()
        return jsonify(simulate_zones(zones, reduction, beta=settings.simulation_beta))

    # ---- Environnement ----
    @app.get("/api/v1/environment/latest")
    def environment_latest():
        area_id = _require_area_id()
        row = get_environment_latest(area_id)
        if not row:
            raise _ApiError("Not found", 404)
        return jsonify(row)

    @app.get("/api/v1/environment/series")
    def environment_series():
        area_id = _require_area_id()
        hours = _bounded_int("hours", default=72, lo=1, hi=24 * 30)
        return jsonify({"area_id": area_id, "items": get_environment_series(area_id, lookback_hours=hours)})

    # ---- Prédictions ----
    @app.get("/api/v1/predictions")
    def predictions():
        area_id = _require_area_id()
        horizon_minutes = _bounded_int("horizon_minutes", default=120, lo=5, hi=1440)
        step_minutes = _bounded_int("step_minutes", default=5, lo=1, hi=60)
        try:
            res = forecast(area_id, horizon_minutes=horizon_minutes, step_minutes=step_minutes)
        except ValueError as e:
            raise _ApiError(str(e), 404) from e
        return jsonify({"area_id": area_id, "model": res.model_name, "items": res.points})

    @app.get("/api/v1/predictions/eval")
    def predictions_eval():
        area_id = _require_area_id()
        try:
            res = evaluate_area(area_id)
        except ValueError as e:
            raise _ApiError(str(e), 404) from e
        return jsonify(res)

    # ---- Recommandations ----
    @app.get("/api/v1/recommendations")
    def recommendations():
        area_id = _require_area_id()
        try:
            res = recommend(area_id)
        except ValueError as e:
            raise _ApiError(str(e), 404) from e
        return jsonify(res)

    # ---- Signalements citoyens ----
    @app.get("/api/v1/crowd_reports")
    def crowd_reports_list():
        area_id = request.args.get("area_id", type=str)
        limit = _bounded_int("limit", default=200, lo=1, hi=settings.max_page_limit)
        offset = _bounded_int("offset", default=0, lo=0, hi=10_000_000)
        items = list_crowd_reports(area_id=area_id, limit=limit, offset=offset)
        total = count_crowd_reports(area_id=area_id)
        return jsonify({"items": items, "total": total, "limit": limit, "offset": offset})

    @app.post("/api/v1/crowd_reports")
    @limiter.limit(settings.rate_limit_write)
    @require_api_key
    def crowd_reports_create():
        body = request.get_json(silent=True) or {}
        payload = CrowdReportIn.model_validate(body)  # lève ValidationError -> 400
        report = {
            "id": str(uuid4()),
            "area_id": payload.area_id,
            "ts": datetime.now(tz=timezone.utc).isoformat(),
            "category": payload.category,
            "severity": payload.severity,
            "description": payload.description,
            "status": "open",
        }
        insert_crowd_report(report)
        return jsonify(report), 201

    # ---- Itinéraire avec prédiction des perturbations ----
    @app.post("/api/v1/route")
    @limiter.limit("30 per minute")
    def route():
        body = request.get_json(silent=True) or {}
        payload = RouteIn.model_validate(body)
        try:
            origin = geocode(payload.origin)
            destination = geocode(payload.destination)
            raw_routes = fetch_osrm_routes(origin, destination)
        except RouteNotFound as e:
            raise _ApiError(str(e), 404) from e
        except RoutingUnavailable as e:
            raise _ApiError(str(e), 503) from e

        zones = list_areas()
        max_dur = max(r["duration_s"] for r in raw_routes)
        horizon = int(payload.depart_in_minutes + max_dur / 60.0 + 10)

        def forecast_fn(zone_id: str, h: int):
            res = forecast(zone_id, horizon_minutes=max(h, 15), step_minutes=5)
            return [(datetime.fromisoformat(p["ts"]), float(p["congestion_index"])) for p in res.points]

        def latest_fn(zone_id: str):
            row = get_latest_traffic(zone_id)
            return float(row["congestion_index"]) if row else None

        # Fournisseur de congestion partagé : la prévision par zone est calculée une
        # seule fois et réutilisée pour évaluer toutes les alternatives.
        provider = make_time_congestion_provider(forecast_fn, latest_fn, horizon)
        built: list[dict] = []
        for raw in raw_routes:
            try:
                built.append(
                    build_route_result(
                        raw["coordinates"],
                        raw["distance_m"],
                        raw["duration_s"],
                        zones,
                        provider,
                        depart_in_minutes=payload.depart_in_minutes,
                        penalty=settings.route_congestion_penalty,
                    )
                )
            except RouteNotFound:
                continue
        if not built:
            raise _ApiError("Aucun itinéraire exploitable.", 404)

        # Classement par durée prévue (perturbations incluses) : le 1er est le plus rapide.
        built.sort(key=lambda r: r["duration_adjusted_min"])
        for rank, r in enumerate(built):
            r["label"] = f"Itinéraire {rank + 1}"
            r["rank"] = rank
            r["fastest"] = rank == 0

        return jsonify(
            {
                "origin": {"address": payload.origin, "lat": origin[0], "lon": origin[1]},
                "destination": {"address": payload.destination, "lat": destination[0], "lon": destination[1]},
                "model": "arima+mlp",
                "best_index": 0,
                "count": len(built),
                "routes": built,
            }
        )

    # ---- Observabilité ETL ----
    @app.get("/api/v1/etl/runs")
    def etl_runs():
        limit = _bounded_int("limit", default=50, lo=1, hi=500)
        return jsonify({"items": list_etl_runs(limit=limit)})

    return app


app = create_app()
