from __future__ import annotations

from pydantic import BaseModel, Field, ValidationError, field_validator

ALLOWED_CATEGORIES = {"accident", "chantier", "danger", "transport", "embouteillage", "autre"}


class CrowdReportIn(BaseModel):
    """Validation stricte du corps de POST /api/v1/crowd_reports."""

    area_id: str = Field(min_length=1, max_length=64)
    category: str = Field(min_length=1, max_length=32)
    severity: int = Field(ge=1, le=5)
    description: str | None = Field(default=None, max_length=1000)

    @field_validator("category")
    @classmethod
    def _check_category(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in ALLOWED_CATEGORIES:
            raise ValueError(f"category doit être l'une de {sorted(ALLOWED_CATEGORIES)}")
        return v

    @field_validator("area_id")
    @classmethod
    def _strip_area(cls, v: str) -> str:
        return v.strip()


class Pagination(BaseModel):
    limit: int = Field(default=200, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class RouteIn(BaseModel):
    """Validation du corps de POST /api/v1/route."""

    origin: str = Field(min_length=2, max_length=200)
    destination: str = Field(min_length=2, max_length=200)
    depart_in_minutes: int = Field(default=0, ge=0, le=1440)

    @field_validator("origin", "destination")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


__all__ = ["CrowdReportIn", "Pagination", "RouteIn", "ValidationError", "ALLOWED_CATEGORIES"]
