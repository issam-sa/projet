from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


def build_engine() -> Engine:
    database_url = os.getenv("DATABASE_URL", "postgresql+psycopg://mobility:mobility@localhost:5432/mobility")
    return create_engine(database_url, pool_pre_ping=True, future=True)


engine = build_engine()

