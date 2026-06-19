from __future__ import annotations

import os


def env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value


def _csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


class Settings:
    def __init__(self) -> None:
        self.env = env("ENV", "dev")
        self.database_url = env(
            "DATABASE_URL",
            "postgresql+psycopg://mobility:mobility@localhost:5432/mobility",
        )
        # Sécurité / API
        self.cors_origins = _csv(env("CORS_ORIGINS", "*")) or ["*"]
        self.api_key = env("API_KEY")  # si défini, requis sur les écritures
        self.rate_limit_default = env("RATE_LIMIT_DEFAULT", "200 per minute")
        self.rate_limit_write = env("RATE_LIMIT_WRITE", "20 per minute")
        self.log_level = env("LOG_LEVEL", "INFO")
        # Bornes de validation
        self.max_page_limit = int(env("MAX_PAGE_LIMIT", "500"))
        # Itinéraire (services externes de géocodage / routage)
        self.nominatim_url = env("NOMINATIM_URL", "https://nominatim.openstreetmap.org/search")
        self.osrm_url = env("OSRM_URL", "http://router.project-osrm.org")
        self.routing_user_agent = env(
            "ROUTING_USER_AGENT", "mobilite-projet-etude/1.0 (projet etudiant)"
        )
        self.route_congestion_penalty = float(env("ROUTE_CONGESTION_PENALTY", "1.0"))
        # Simulation what-if : exposant de sensibilité congestion/volume
        self.simulation_beta = float(env("SIMULATION_BETA", "0.8"))


settings = Settings()
