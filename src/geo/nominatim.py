"""Cached, rate-limited client for the public Nominatim search API.

Usage policy: https://operations.osmfoundation.org/policies/nominatim/ .
This client is built to follow it, and whoever runs it is responsible for
doing so: at most 1 request per second from a single thread, an identifying
User-Agent, every response cached so no query is sent twice, no personal data
in queries, and "© OpenStreetMap contributors" (ODbL) credited wherever the
coordinates are published. That suits a one-time job of a few hundred to a
couple of thousand requests. A recurring or much larger job needs another
provider or a self-hosted Nominatim.

A 403 or 429 raises NominatimBlocked: the caller stops, it doesn't retry.
"""
from __future__ import annotations

import json
import sqlite3
import time
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests

from src.geo.address import CITY, Candidate, area_candidate, pick_result

ENDPOINT = "https://nominatim.openstreetmap.org/search"
DEFAULT_USER_AGENT = (
    "VietnamRentalRoom-research/0.1 (USTH academic project; one-time geocoding of Hanoi rental listings)"
)
ATTRIBUTION = "© OpenStreetMap contributors (data under ODbL), geocoded with Nominatim"
HANOI_VIEWBOX = "105.25,21.45,106.05,20.50"
VIETNAM_VIEWBOX = "102.10,23.40,109.50,8.20"   # for addresses in another province
BOX_PAD_DEG = 0.005   # ~500 m, so a listing on a district's edge isn't cut off
MIN_INTERVAL_S = 1.1
BASE_PARAMS = {
    "format": "jsonv2", "addressdetails": "1", "limit": "5", "countrycodes": "vn",
    "accept-language": "vi", "bounded": "1",
}


class NominatimBlocked(Exception):
    """Nominatim refused service (HTTP 403/429)."""


@dataclass(frozen=True)
class GeoResult:
    lat: float
    lon: float
    level: str
    query: str
    display_name: str


class NominatimGeocoder:
    def __init__(
        self,
        cache_path: Path,
        user_agent: str = DEFAULT_USER_AGENT,
        *,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        max_requests: int | None = None,
        offline: bool = False,
    ):
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(cache_path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS nominatim_cache (key TEXT PRIMARY KEY, status INTEGER NOT NULL, "
            "response TEXT NOT NULL, fetched_at TEXT NOT NULL)"
        )
        self.user_agent = user_agent
        self._session = session or requests.Session()
        self._sleep = sleep
        self._clock = clock
        self.max_requests = max_requests
        self.offline = offline
        self.n_requests = 0
        self.n_cache_hits = 0
        self._last_request_at = float("-inf")
        self._viewboxes: dict[tuple[str, str], str] = {}

    def close(self) -> None:
        self._conn.close()

    def search(self, query: str, viewbox: str = HANOI_VIEWBOX) -> list[dict] | None:
        """Results for one query, or None if it isn't cached and no request may be sent."""
        params = dict(BASE_PARAMS, q=query, viewbox=viewbox)
        key = "search?" + urllib.parse.urlencode(sorted(params.items()))
        row = self._conn.execute("SELECT response FROM nominatim_cache WHERE key=?", (key,)).fetchone()
        if row:
            self.n_cache_hits += 1
            return json.loads(row[0])
        if self.offline or (self.max_requests is not None and self.n_requests >= self.max_requests):
            return None

        for attempt in range(3):
            wait = MIN_INTERVAL_S - (self._clock() - self._last_request_at)
            if wait > 0:
                self._sleep(wait)
            self._last_request_at = self._clock()
            self.n_requests += 1
            try:
                resp = self._session.get(
                    ENDPOINT, params=params, headers={"User-Agent": self.user_agent}, timeout=30
                )
            except requests.RequestException:
                if attempt == 2:
                    raise
                self._sleep(10.0 * (attempt + 1))
                continue
            if resp.status_code in (403, 429):
                raise NominatimBlocked(f"HTTP {resp.status_code} for {query!r}")
            if resp.status_code >= 500 and attempt < 2:
                self._sleep(10.0 * (attempt + 1))
                continue
            resp.raise_for_status()
            break

        self._conn.execute(
            "INSERT OR REPLACE INTO nominatim_cache VALUES (?,?,?,?)",
            (key, resp.status_code, resp.text, datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()
        return resp.json()

    def area_viewbox(self, candidate: Candidate) -> str | None:
        """Padded box that bounds this candidate's search.

        Its legacy district's historic boundary, or its own city's when the
        address isn't in Hanoi. Falls back to the whole city/country when the
        area is unknown to OSM; None when the area lookup itself couldn't be
        sent (offline or out of budget).
        """
        outer = HANOI_VIEWBOX if candidate.city == CITY else VIETNAM_VIEWBOX
        area = candidate.city if candidate.city != CITY else candidate.district
        if not area:
            return outer
        key = (area, candidate.city)
        if key in self._viewboxes:
            return self._viewboxes[key]
        area_query = area_candidate(area, candidate.city)
        results = self.search(area_query.query, outer)
        if results is None:
            return None
        match = pick_result(area_query, results)
        if match is None or "boundingbox" not in match:
            box = outer
        else:
            south, north, west, east = map(float, match["boundingbox"])
            box = (f"{west - BOX_PAD_DEG:.6f},{north + BOX_PAD_DEG:.6f},"
                   f"{east + BOX_PAD_DEG:.6f},{south - BOX_PAD_DEG:.6f}")
        self._viewboxes[key] = box
        return box

    def geocode(self, candidates: list[Candidate]) -> tuple[GeoResult | None, bool]:
        """First candidate with a result that passes the checks in src/geo/address.py.

        The flag is False when a lookup this needed couldn't be sent, i.e. the
        answer is unknown rather than "not found".
        """
        for candidate in candidates:
            if candidate.level in ("district", "city"):
                box = HANOI_VIEWBOX if candidate.city == CITY else VIETNAM_VIEWBOX
            else:
                box = self.area_viewbox(candidate)
            if box is None:
                return None, False
            results = self.search(candidate.query, box)
            if results is None:
                return None, False
            match = pick_result(candidate, results)
            if match is not None:
                return GeoResult(
                    lat=float(match["lat"]), lon=float(match["lon"]), level=candidate.level,
                    query=candidate.query, display_name=match.get("display_name", ""),
                ), True
        return None, True
