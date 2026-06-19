import pytest

import app.main as main


@pytest.fixture()
def client():
    main.app.config.update(TESTING=True)
    return main.app.test_client()


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


def test_areas(monkeypatch, client):
    monkeypatch.setattr(main, "list_areas", lambda: [{"id": "a", "name": "A", "lat": 1.0, "lon": 2.0}])
    resp = client.get("/api/v1/areas")
    assert resp.status_code == 200
    assert resp.get_json()["items"][0]["id"] == "a"


def test_traffic_latest_requires_area_id(client):
    resp = client.get("/api/v1/traffic/latest")
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["error"]
    assert body["code"] == 400


def test_crowd_report_validation_error(client):
    resp = client.post("/api/v1/crowd_reports", json={"area_id": "a", "category": "banane", "severity": 9})
    assert resp.status_code == 400
    assert "details" in resp.get_json()


def test_crowd_report_create_ok(monkeypatch, client):
    saved = {}
    monkeypatch.setattr(main, "insert_crowd_report", lambda report: saved.update(report))
    resp = client.post(
        "/api/v1/crowd_reports",
        json={"area_id": "paris_centre", "category": "accident", "severity": 3, "description": "test"},
    )
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["status"] == "open"
    assert body["category"] == "accident"
    assert saved["area_id"] == "paris_centre"


def test_crowd_reports_pagination(monkeypatch, client):
    monkeypatch.setattr(main, "list_crowd_reports", lambda area_id, limit, offset: [])
    monkeypatch.setattr(main, "count_crowd_reports", lambda area_id: 0)
    resp = client.get("/api/v1/crowd_reports?limit=10&offset=5")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["limit"] == 10
    assert body["offset"] == 5
    assert body["total"] == 0
