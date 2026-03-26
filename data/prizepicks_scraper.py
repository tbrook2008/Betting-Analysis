"""
data/prizepicks_scraper.py — PrizePicks partner API scraper.

Endpoint: https://partner-api.prizepicks.com/projections?league_id=2
Returns a normalized DataFrame of MLB player props.
"""
from __future__ import annotations

from typing import Optional

import httpx
import pandas as pd

import config
from utils.cache import cached
from utils.logger import get_logger

log = get_logger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; BettingAnalysis/1.0)",
    "Accept": "application/json",
    "Origin": "https://app.prizepicks.com",
    "Referer": "https://app.prizepicks.com/",
}


@cached(ttl=config.CACHE_TTL_LINES, key_prefix="prizepicks_mlb")
def get_prizepicks_lines(league_id: str = config.PRIZEPICKS_MLB_LEAGUE_ID) -> pd.DataFrame:
    """
    Fetch MLB player prop lines from PrizePicks partner API.

    Returns a DataFrame with columns:
        player_name, team, position, prop_type, line_score,
        game_time, opponent, is_promo
    """
    url = f"{config.PRIZEPICKS_API_BASE}/projections"
    params = {
        "league_id": league_id,
        "per_page": 250,
        "single_stat": True,
    }

    try:
        resp = httpx.get(url, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        payload = resp.json()
    except httpx.HTTPStatusError as e:
        log.error(f"PrizePicks API error {e.response.status_code}: {e}")
        return pd.DataFrame()
    except Exception as exc:
        log.error(f"PrizePicks fetch failed: {exc}")
        return pd.DataFrame()

    return _parse_prizepicks_response(payload)


def _parse_prizepicks_response(payload: dict) -> pd.DataFrame:
    """
    Parse JSON:API response from PrizePicks.

    The payload has:
        data[]       → projections (each has relationships to player/stat_type)
        included[]   → player and stat_type objects
    """
    data = payload.get("data", [])
    included = payload.get("included", [])

    # Build lookup maps from included resources
    players: dict[str, dict] = {}
    stat_types: dict[str, str] = {}
    games: dict[str, dict] = {}

    for obj in included:
        obj_type = obj.get("type")
        obj_id = obj.get("id")
        attrs = obj.get("attributes", {})

        if obj_type == "new_player":
            players[obj_id] = {
                "name": attrs.get("display_name") or attrs.get("name", ""),
                "team": attrs.get("team", ""),
                "position": attrs.get("position", ""),
            }
        elif obj_type == "stat_type":
            stat_types[obj_id] = attrs.get("name", "")
        elif obj_type == "game":
            games[obj_id] = {
                "start_time": attrs.get("start_time") or attrs.get("scheduled_at", ""),
                "away_team": attrs.get("away_team", ""),
                "home_team": attrs.get("home_team", ""),
                "home_team_id": attrs.get("home_team_id", ""),
                "away_team_id": attrs.get("away_team_id", ""),
            }

    rows = []
    for proj in data:
        if proj.get("type") != "projection":
            continue
        attrs = proj.get("attributes", {})
        rels = proj.get("relationships", {})

        # Resolve related IDs
        player_id = _rel_id(rels, "new_player")
        stat_type_id = _rel_id(rels, "stat_type")
        game_id = _rel_id(rels, "game")

        player_info = players.get(player_id, {})
        game_info = games.get(game_id, {})

        player_name = player_info.get("name", attrs.get("player_name", "Unknown"))
        team = player_info.get("team", "")
        # Determine opponent
        opponent = ""
        if game_info:
            if team and team.upper() == game_info.get("home_team", "").upper():
                opponent = game_info.get("away_team", "")
            else:
                opponent = game_info.get("home_team", "")

        rows.append({
            "player_name": player_name,
            "team": team,
            "position": player_info.get("position", ""),
            "prop_type": stat_types.get(stat_type_id, attrs.get("stat_type", "")),
            "line_score": float(attrs.get("line_score", 0) or 0),
            "game_time": game_info.get("start_time", ""),
            "opponent": opponent,
            "is_promo": bool(attrs.get("is_promo", False)),
            "projection_id": proj.get("id", ""),
        })

    df = pd.DataFrame(rows)

    if df.empty:
        log.warning("PrizePicks returned no MLB projections.")
        return df

    # Normalize prop type names
    df["prop_type"] = df["prop_type"].str.strip()

    log.info(
        f"PrizePicks: {len(df)} projections — "
        f"{df['prop_type'].value_counts().to_dict()}"
    )
    return df


def get_prizepicks_by_prop(prop_type: str) -> pd.DataFrame:
    """
    Convenience wrapper — filter PrizePicks lines to a specific prop type.

    Common prop_type values:
        'Hits+Runs+RBIs', 'Home Runs', 'Pitcher Strikeouts',
        'Hits', 'Total Bases', 'Runs', 'RBIs'
    """
    df = get_prizepicks_lines()
    if df.empty:
        return df
    mask = df["prop_type"].str.lower() == prop_type.lower()
    return df[mask].reset_index(drop=True)


def list_prizepicks_prop_types() -> list[str]:
    """Return all distinct prop types currently offered on PrizePicks."""
    df = get_prizepicks_lines()
    if df.empty:
        return []
    return sorted(df["prop_type"].unique().tolist())


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _rel_id(relationships: dict, key: str) -> str:
    """Extract the ID from a JSON:API relationship block."""
    rel = relationships.get(key, {})
    data = rel.get("data")
    if isinstance(data, dict):
        return data.get("id", "")
    if isinstance(data, list) and data:
        return data[0].get("id", "")
    return ""
