import os

import httpx

BASE_URL = os.getenv("FRONTEND_API_URL", "http://localhost:8000")

def get(path: str):
    try:
        response = httpx.get(f"{BASE_URL}{path}", timeout=5)
        response.raise_for_status()
        return response.json(), None
    except (httpx.HTTPError, ValueError) as exc:
        return None, str(exc)

def post(path: str, payload: dict):
    try:
        response = httpx.post(f"{BASE_URL}{path}", json=payload, timeout=90)
        response.raise_for_status()
        return response.json(), None
    except (httpx.HTTPError, ValueError) as exc:
        detail = getattr(getattr(exc, "response", None), "text", "")
        return None, detail or str(exc)

def patch(path: str, payload: dict | None = None):
    try:
        response = httpx.patch(f"{BASE_URL}{path}", json=payload or {}, timeout=15)
        response.raise_for_status()
        return response.json(), None
    except (httpx.HTTPError, ValueError) as exc:
        detail = getattr(getattr(exc, "response", None), "text", "")
        return None, detail or str(exc)

def download(path: str):
    try:
        response = httpx.get(f"{BASE_URL}{path}", timeout=30)
        response.raise_for_status()
        return response.content, response.headers.get("content-type", "application/octet-stream"), None
    except httpx.HTTPError as exc:
        return None, None, str(exc)
