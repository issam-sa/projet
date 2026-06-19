from datetime import datetime, timedelta, timezone

from app.routing import (
    build_route_result,
    congestion_color,
    haversine_m,
    make_time_congestion_provider,
    nearest_zone,
)


def test_haversine_paris():
    # Tour Eiffel -> Gare du Nord (~4-5 km à vol d'oiseau)
    d = haversine_m(48.8584, 2.2945, 48.8809, 2.3553)
    assert 3000 < d < 6000


def test_nearest_zone():
    zones = [
        {"id": "a", "name": "A", "lat": 48.86, "lon": 2.30},
        {"id": "b", "name": "B", "lat": 48.90, "lon": 2.40},
    ]
    z = nearest_zone(48.861, 2.301, zones)
    assert z["id"] == "a"


def test_congestion_color_thresholds():
    assert congestion_color(0.1) == [40, 180, 80]    # vert
    assert congestion_color(0.5) == [240, 170, 40]   # orange
    assert congestion_color(0.9) == [220, 50, 50]    # rouge
    assert congestion_color(None) == [130, 130, 130]  # inconnu


def test_build_route_result_adjusts_duration():
    coords = [[2.30, 48.86], [2.31, 48.86], [2.32, 48.86]]
    zones = [{"id": "z1", "name": "Z1", "lat": 48.86, "lon": 2.31}]

    def congestion_at(zone_id, passage_dt):
        return 0.5

    res = build_route_result(
        coords, distance_m=1000.0, duration_s=600.0, zones=zones,
        congestion_at=congestion_at, depart_in_minutes=0, penalty=1.0,
    )
    assert res["duration_min"] == 10.0
    # 600s * (1 + 1*0.5) = 900s = 15 min
    assert res["duration_adjusted_min"] == 15.0
    assert res["delay_min"] == 5.0
    assert len(res["segments"]) == 1
    assert res["segments"][0]["zone_id"] == "z1"
    assert res["segments"][0]["color"] == [240, 170, 40]
    assert res["zones_traversed"][0]["zone_id"] == "z1"


def test_congestion_provider_series_and_fallback():
    now = datetime(2026, 6, 7, 12, 0, tzinfo=timezone.utc)

    def forecast_ok(zone_id, horizon):
        return [(now, 0.2), (now + timedelta(minutes=10), 0.8)]

    def latest(zone_id):
        return 0.33

    provider = make_time_congestion_provider(forecast_ok, latest, horizon_minutes=30)
    # passage proche de now -> 0.2 ; proche de now+10 -> 0.8
    assert provider("z", now + timedelta(minutes=1)) == 0.2
    assert provider("z", now + timedelta(minutes=9)) == 0.8

    def forecast_fail(zone_id, horizon):
        raise RuntimeError("pas de données")

    provider2 = make_time_congestion_provider(forecast_fail, latest, horizon_minutes=30)
    assert provider2("z", now) == 0.33  # fallback latest
