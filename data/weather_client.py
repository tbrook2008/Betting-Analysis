"""
data/weather_client.py — Game-day weather and venue condition signals.

Uses OpenWeatherMap free API (60 calls/min) to provide wind/temp context
for park factor adjustments. Wind > 15 mph OUT boosts HR; INTO penalizes.
Set OPENWEATHER_API_KEY in .env to activate. Gracefully returns neutral
signals if no key is provided.
"""
from __future__ import annotations

import os
import logging
import httpx
from typing import Optional
from functools import lru_cache
from utils import cache

log = logging.getLogger(__name__)

_OWM_BASE = "https://api.openweathermap.org/data/2.5"

# Approximate lat/lon for MLB stadiums
_STADIUM_COORDS: dict[str, tuple[float, float]] = {
    "Yankee Stadium":           (40.829, -73.926),
    "Fenway Park":              (42.346, -71.097),
    "Wrigley Field":            (41.948, -87.656),
    "Dodger Stadium":           (34.074, -118.240),
    "Great American Ball Park": (39.097, -84.506),
    "Camden Yards":             (39.284, -76.622),
    "Busch Stadium":            (38.623, -90.193),
    "Chase Field":              (33.445, -112.067),     # retractable roof
    "Citizens Bank Park":       (39.906, -75.166),
    "Petco Park":               (32.707, -117.157),
    "Oracle Park":              (37.779, -122.389),
    "Globe Life Field":         (32.747, -97.082),      # retractable roof
    "T-Mobile Park":            (47.591, -122.332),     # retractable roof
    "Coors Field":              (39.756, -104.994),
    "American Family Field":    (43.028, -87.971),      # retractable roof
    "Minute Maid Park":         (29.757, -95.356),      # retractable roof
    "loanDepot park":           (25.778, -80.220),      # retractable roof
    "Target Field":             (44.982, -93.278),
    "Kauffman Stadium":         (39.052, -94.480),
    "PNC Park":                 (40.447, -80.006),
    "Truist Park":              (33.891, -84.468),
    "Angel Stadium":            (33.800, -117.883),
    "Oakland Coliseum":         (37.752, -122.201),
    "Citi Field":               (40.757, -73.846),
    "Nationals Park":           (38.873, -77.008),
    "Tropicana Field":          (27.768, -82.653),      # dome
    "Progressive Field":        (41.496, -81.685),
    "Comerica Park":            (42.339, -83.049),
    "Rogers Centre":            (43.641, -79.389),      # retractable roof
    "Guaranteed Rate Field":    (41.830, -87.634),
}

# Stadiums with roofs / domes — weather irrelevant
_ROOFED_STADIUMS = {
    "Chase Field", "Globe Life Field", "T-Mobile Park",
    "American Family Field", "Minute Maid Park", "loanDepot park",
    "Tropicana Field", "Rogers Centre",
}


@lru_cache(maxsize=64)
def _owm_weather(lat: float, lon: float) -> dict:
    """Raw OpenWeatherMap current conditions call (cached per location)."""
    api_key = os.getenv("OPENWEATHER_API_KEY")
    if not api_key:
        return {}
    try:
        resp = httpx.get(
            f"{_OWM_BASE}/weather",
            params={"lat": lat, "lon": lon, "appid": api_key, "units": "imperial"},
            timeout=5,
        )
        return resp.json() if resp.status_code == 200 else {}
    except Exception as exc:
        log.debug(f"Weather fetch failed: {exc}")
        return {}


def get_weather_signals(venue: str) -> dict[str, float]:
    """
    Return weather adjustment signals for a stadium.

    Returns a dict with keys:
      wind_mph         — current wind speed in mph
      wind_out_boost   — positive if wind is blowing out (HR boost)
      wind_in_penalty  — positive if wind is blowing in (HR/hits penalty)
      temp_f           — temperature in Fahrenheit
      temp_boost       — positive in warm weather (ball travels farther)
      is_dome          — 1.0 if retractable roof/dome (all other signals irrelevant)
    """
    if venue in _ROOFED_STADIUMS:
        return {"is_dome": 1.0}

    coords = _STADIUM_COORDS.get(venue)
    if not coords:
        return {}  # Unknown venue — return neutral signals

    raw = _owm_weather(*coords)
    if not raw:
        return {}

    wind_speed = raw.get("wind", {}).get("speed", 0.0)   # mph
    wind_deg   = raw.get("wind", {}).get("deg", 0)        # 0 = N, 90 = E
    temp_f     = raw.get("main", {}).get("temp", 70.0)

    signals: dict[str, float] = {
        "wind_mph": wind_speed,
        "temp_f": temp_f,
        "is_dome": 0.0,
    }

    # Simplified wind direction mapping — "blowing out" depends on stadium orientation.
    # We use a generic heuristic: wind from S (≈180°) typically blows out at most parks.
    if wind_speed > 15:
        if 135 <= wind_deg <= 225:  # Southerly — generally hits blow out
            signals["wind_out_boost"] = min((wind_speed - 15) / 10, 1.0)
        elif wind_deg <= 45 or wind_deg >= 315:  # Northerly — heads in
            signals["wind_in_penalty"] = min((wind_speed - 15) / 10, 1.0)

    # Warm weather: ball travels farther
    if temp_f >= 80:
        signals["temp_boost"] = min((temp_f - 80) / 20, 0.5)
    elif temp_f <= 50:
        signals["temp_boost"] = -min((50 - temp_f) / 20, 0.5)

    return signals
