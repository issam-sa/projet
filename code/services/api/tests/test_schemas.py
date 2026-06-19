import pytest

from app.schemas import CrowdReportIn, Pagination, ValidationError


def test_crowd_report_valid():
    r = CrowdReportIn.model_validate(
        {"area_id": " paris_centre ", "category": "Accident", "severity": 3, "description": "x"}
    )
    assert r.area_id == "paris_centre"  # strip
    assert r.category == "accident"  # normalisé en minuscules
    assert r.severity == 3


def test_crowd_report_invalid_severity():
    with pytest.raises(ValidationError):
        CrowdReportIn.model_validate({"area_id": "a", "category": "accident", "severity": 6})


def test_crowd_report_invalid_category():
    with pytest.raises(ValidationError):
        CrowdReportIn.model_validate({"area_id": "a", "category": "banane", "severity": 2})


def test_pagination_bounds():
    assert Pagination().limit == 200
    with pytest.raises(ValidationError):
        Pagination(limit=10_000)
