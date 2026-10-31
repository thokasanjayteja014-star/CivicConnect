"""Address search and reverse geocoding through a server-side proxy.

Default provider: OpenStreetMap Nominatim (free, no key). Its usage policy asks
for an identifying User-Agent, at most 1 request per second and caching, so all
three are enforced here. Results are suggestions: the citizen still confirms
the pin on the map, and routing uses the confirmed coordinates.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict

import httpx
from fastapi import APIRouter, Depends, Query

from app.core.config import get_settings
from app.core.errors import err
from app.security.deps import get_current_actor
from app.security.permissions import Actor

router = APIRouter(prefix="/api/geo", tags=["geo"])

_lock = threading.Lock()
_last_call = 0.0
_cache: OrderedDict[str, object] = OrderedDict()
_CACHE_MAX = 500


def _cached(key: str):
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    return None


def _store(key: str, value) -> None:
    _cache[key] = value
    if len(_cache) > _CACHE_MAX:
        _cache.popitem(last=False)


def _get(path: str, params: dict) -> object:
    global _last_call
    s = get_settings()
    lang = params.pop("_lang", "en")
    ua = "CivicConnect/1.0" + (f" ({s.GEOCODER_CONTACT_EMAIL})" if s.GEOCODER_CONTACT_EMAIL else "")
    with _lock:  # serialise calls: max 1 request/second to the provider
        wait = 1.0 - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        try:
            r = httpx.get(s.GEOCODER_URL.rstrip("/") + path, params={**params, "format": "jsonv2"},
                          headers={"User-Agent": ua, "Accept-Language": lang}, timeout=10)
        except httpx.HTTPError:
            raise err("GEOCODER_UNAVAILABLE")
        finally:
            _last_call = time.monotonic()
    if r.status_code != 200:
        raise err("GEOCODER_UNAVAILABLE")
    try:
        return r.json()
    except ValueError:
        raise err("GEOCODER_UNAVAILABLE")


def _place(p: dict) -> dict:
    return {"display_name": p.get("display_name"), "latitude": float(p["lat"]), "longitude": float(p["lon"]),
            "type": p.get("type"), "importance": p.get("importance")}


@router.get("/search")
def search(q: str = Query(min_length=3, max_length=200), lang: str = Query("en", pattern="^(en|hi|kn)$"),
           actor: Actor = Depends(get_current_actor)):
    """Find places matching an address or landmark (max 5 results)."""
    s = get_settings()
    key = f"s:{lang}:{q.strip().lower()}"
    hit = _cached(key)
    if hit is None:
        params = {"q": q.strip(), "limit": 5, "addressdetails": 0, "_lang": lang}
        if s.GEOCODER_COUNTRY_CODES:
            params["countrycodes"] = s.GEOCODER_COUNTRY_CODES
        data = _get("/search", params)
        hit = [_place(p) for p in data if isinstance(p, dict) and "lat" in p and "lon" in p] if isinstance(data, list) else []
        _store(key, hit)
    return {"results": hit, "attribution": "Search data © OpenStreetMap contributors"}


@router.get("/reverse")
def reverse(lat: float = Query(ge=-90, le=90), lng: float = Query(ge=-180, le=180),
            lang: str = Query("en", pattern="^(en|hi|kn)$"), actor: Actor = Depends(get_current_actor)):
    """Nearest address for a map point. Coordinates are rounded to ~11 m for caching."""
    key = f"r:{lang}:{lat:.4f},{lng:.4f}"
    hit = _cached(key)
    if hit is None:
        data = _get("/reverse", {"lat": f"{lat:.6f}", "lon": f"{lng:.6f}", "zoom": 18, "_lang": lang})
        hit = {"display_name": data.get("display_name")} if isinstance(data, dict) and data.get("display_name") else {"display_name": None}
        _store(key, hit)
    return {**hit, "attribution": "Address data © OpenStreetMap contributors"}
