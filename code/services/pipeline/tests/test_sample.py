from pipeline.sources.sample import default_areas, generate_environment, generate_traffic


def test_default_areas_unique_ids():
    areas = default_areas()
    ids = [a.id for a in areas]
    assert len(ids) == len(set(ids))
    assert "paris_centre" in ids


def test_generate_traffic_schema_and_bounds():
    df = generate_traffic(days=2)
    assert not df.empty
    assert set(["area_id", "ts", "speed_kph", "volume_veh_h", "congestion_index", "source"]).issubset(df.columns)
    assert df["congestion_index"].between(0.0, 1.0).all()
    assert (df["source"] == "sample").all()


def test_generate_traffic_is_deterministic():
    a = generate_traffic(days=1)
    b = generate_traffic(days=1)
    assert a["congestion_index"].tolist() == b["congestion_index"].tolist()


def test_generate_environment_schema():
    df = generate_environment(days=2)
    assert not df.empty
    assert set(["area_id", "ts", "temperature_c", "pm2_5", "no2", "o3", "us_aqi", "source"]).issubset(df.columns)
