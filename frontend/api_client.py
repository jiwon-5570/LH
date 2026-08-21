import os

import httpx

BASE_URL = os.getenv("FRONTEND_API_URL", "http://localhost:8000")

# Local dashboard-to-API traffic must not use Windows/system proxy discovery.
# Reusing one client also avoids a TCP setup on every Streamlit rerun.
_CLIENT = httpx.Client(
    base_url=BASE_URL,
    trust_env=False,
    timeout=httpx.Timeout(15.0, connect=3.0),
)

def get(path: str):
    try:
        response = _CLIENT.get(path, timeout=5)
        response.raise_for_status()
        return response.json(), None
    except (httpx.HTTPError, ValueError) as exc:
        return None, str(exc)

def post(path: str, payload: dict):
    try:
        response = _CLIENT.post(path, json=payload, timeout=90)
        response.raise_for_status()
        return response.json(), None
    except (httpx.HTTPError, ValueError) as exc:
        detail = getattr(getattr(exc, "response", None), "text", "")
        return None, detail or str(exc)

def patch(path: str, payload: dict | None = None):
    try:
        response = _CLIENT.patch(path, json=payload or {}, timeout=15)
        response.raise_for_status()
        return response.json(), None
    except (httpx.HTTPError, ValueError) as exc:
        detail = getattr(getattr(exc, "response", None), "text", "")
        return None, detail or str(exc)

def download(path: str):
    try:
        response = _CLIENT.get(path, timeout=30)
        response.raise_for_status()
        return response.content, response.headers.get("content-type", "application/octet-stream"), None
    except httpx.HTTPError as exc:
        return None, None, str(exc)
