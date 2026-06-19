from __future__ import annotations

import time

from flask import Flask, Response, g, request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Nombre total de requêtes HTTP",
    ["method", "endpoint", "status"],
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "Latence des requêtes HTTP (secondes)",
    ["method", "endpoint"],
)


def init_metrics(app: Flask) -> None:
    @app.before_request
    def _start_timer() -> None:
        g._start_time = time.perf_counter()

    @app.after_request
    def _record(response: Response) -> Response:
        endpoint = request.endpoint or "unknown"
        if endpoint != "metrics":
            elapsed = time.perf_counter() - getattr(g, "_start_time", time.perf_counter())
            REQUEST_LATENCY.labels(request.method, endpoint).observe(elapsed)
            REQUEST_COUNT.labels(request.method, endpoint, response.status_code).inc()
        return response

    @app.get("/metrics")
    def metrics() -> Response:
        return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)
