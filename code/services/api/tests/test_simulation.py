from app.simulation import simulate_congestion, simulate_zones


def test_simulate_congestion_no_reduction():
    assert simulate_congestion(0.5, 0, beta=0.8) == 0.5


def test_simulate_congestion_half_volume_linear():
    # beta=1, -50% => facteur 0.5 => 0.25
    assert abs(simulate_congestion(0.5, 50, beta=1.0) - 0.25) < 1e-9


def test_simulate_congestion_clip():
    assert simulate_congestion(1.0, 0, beta=1.0) == 1.0
    assert simulate_congestion(0.0, 50, beta=1.0) == 0.0


def test_simulate_zones_aggregates():
    zones = [
        {"area_id": "a", "name": "A", "congestion_index": 0.6},
        {"area_id": "b", "name": "B", "congestion_index": 0.4},
    ]
    res = simulate_zones(zones, reduction_pct=50, beta=1.0)
    assert res["zones"] == 2
    assert res["avg_congestion_current"] == 0.5
    # chaque congestion divisée par 2 => moyenne 0.25
    assert res["avg_congestion_simulated"] == 0.25
    assert res["avg_congestion_drop_pct"] == 50.0
    assert res["est_time_gain_pct"] > 0
    assert len(res["items"]) == 2


def test_simulate_zones_skips_missing():
    zones = [
        {"area_id": "a", "name": "A", "congestion_index": None},
        {"area_id": "b", "name": "B", "congestion_index": 0.4},
    ]
    res = simulate_zones(zones, reduction_pct=10, beta=0.8)
    assert res["zones"] == 1
