from __future__ import annotations

import os
from typing import Any

import requests


class ApiClient:
    def __init__(self) -> None:
        self.base_url = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")

    def get(self, path: str, params: dict | None = None) -> Any:
        url = f"{self.base_url}{path}"
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        return r.json()

    def post(self, path: str, json: dict) -> Any:
        url = f"{self.base_url}{path}"
        r = requests.post(url, json=json, timeout=20)
        r.raise_for_status()
        return r.json()

