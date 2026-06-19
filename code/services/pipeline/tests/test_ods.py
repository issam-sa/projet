import pandas as pd

from pipeline.sources import opendatasoft as ods


def test_aggregate_city_traffic_hourly_mean_and_congestion():
    raw = pd.DataFrame(
        [
            {"ts": "2025-01-01T08:00:00+00:00", "volume_veh_h": 100.0, "occupancy": 40.0},
            {"ts": "2025-01-01T08:30:00+00:00", "volume_veh_h": 200.0, "occupancy": 60.0},
            {"ts": "2025-01-01T09:00:00+00:00", "volume_veh_h": 50.0, "occupancy": 120.0},
        ]
    )
    out = ods.aggregate_city_traffic(raw)
    assert list(out.columns) == ["ts", "volume_veh_h", "congestion_index"]
    # 08:00 et 08:30 -> agrégés sur l'heure 08:00 : occupancy moy = 50 -> congestion 0.5
    row8 = out[out["ts"] == pd.Timestamp("2025-01-01T08:00:00", tz="UTC")].iloc[0]
    assert abs(row8["congestion_index"] - 0.5) < 1e-9
    assert abs(row8["volume_veh_h"] - 150.0) < 1e-9
    # occupancy 120% -> clip à 1.0
    row9 = out[out["ts"] == pd.Timestamp("2025-01-01T09:00:00", tz="UTC")].iloc[0]
    assert row9["congestion_index"] == 1.0


def test_aggregate_empty():
    out = ods.aggregate_city_traffic(pd.DataFrame())
    assert out.empty


def test_parse_ts_handles_z_suffix():
    dt = ods._parse_ts("2025-01-01T08:00:00Z")
    assert dt.tzinfo is not None
    assert dt.hour == 8


def test_fetch_traffic_records_mocked(monkeypatch):
    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "results": [
                    {"t_1h": "2025-01-01T08:00:00+00:00", "q": 100, "k": 40},
                    {"t_1h": "2025-01-01T09:00:00+00:00", "q": 80, "k": 30},
                ]
            }

    def fake_get(url, params=None, headers=None, timeout=None):
        # Deuxième page vide pour stopper la pagination
        if params and params.get("offset", 0) > 0:
            class Empty(FakeResp):
                def json(self):
                    return {"results": []}

            return Empty()
        return FakeResp()

    monkeypatch.setattr(ods.requests, "get", fake_get)
    df = ods.fetch_traffic_records("opendata.paris.fr", "comptages-routiers-permanents", max_records=200)
    assert len(df) == 2
    assert set(df.columns) == {"ts", "volume_veh_h", "occupancy"}
    assert df.iloc[0]["occupancy"] == 40.0
