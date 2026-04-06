"""
data/draftkings_scraper.py — DraftKings player prop lines.

Primary:  The Odds API (free tier, requires ODDS_API_KEY in .env)
Fallback: Returns empty DataFrame with a warning if no key is set.

The Odds API docs: https://the-odds-api.com/lol-api/sports/baseball_mlb/odds
"""
from __future__ import annotations

from typing import Optional

import httpx
import pandas as pd

import config
from utils.cache import cached
from utils.http import retry
from utils.logger import get_logger

log = get_logger(__name__)

# Prop markets available through The Odds API for player props
_PLAYER_PROP_MARKETS = [
    "batter_hits",
    "batter_home_runs",
    "batter_rbis",
    "batter_runs_scored",
    "batter_total_bases",
    "pitcher_strikeouts",
    "pitcher_outs",
]

# Mapping from odds-api market name → our internal prop_type label
_MARKET_LABEL_MAP = {
    "batter_hits": "Hits",
    "batter_home_runs": "Home Runs",
    "batter_rbis": "RBIs",
    "batter_runs_scored": "Runs",
    "batter_total_bases": "Total Bases",
    "pitcher_strikeouts": "Pitcher Strikeouts",
    "pitcher_outs": "Pitcher Outs",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; BettingAnalysis/1.0)",
    "Accept": "application/json",
}


@retry(max_retries=2)
@cached(ttl=config.CACHE_TTL_LINES, key_prefix="draftkings_mlb")
def get_draftkings_lines() -> pd.DataFrame:
    """
    Fetch MLB player prop lines from The Odds API (DraftKings bookmaker).
    Uses the per-event endpoint for player props as required by The Odds API.
    """
    if not config.ODDS_API_KEY:
        log.warning("ODDS_API_KEY not set — DraftKings lines unavailable.")
        return pd.DataFrame()

    # 1. Fetch today's events to get IDs
    events = _fetch_events()
    if not events:
        log.warning("DraftKings: No MLB events found for today.")
        return pd.DataFrame()

    all_rows: list[dict] = []
    
    # 2. Fetch props for each event (Parallelized to avoid slow sequential calls)
    import os
    from concurrent.futures import ThreadPoolExecutor
    
    markets_str = ",".join(_PLAYER_PROP_MARKETS)
    
    def _fetch_event_props(event: dict) -> list[dict]:
        event_id = event.get("id")
        if not event_id: return []
        return _fetch_event_market(event_id, markets_str)

    with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as executor:
        results = list(executor.map(_fetch_event_props, events))
        for rows in results:
            all_rows.extend(rows)

    if not all_rows:
        log.warning("DraftKings: no player prop data returned.")
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)
    log.info(
        f"DraftKings: {len(df)} player prop lines across "
        f"{df['prop_type'].nunique()} markets"
    )
    return df


def _fetch_events() -> list[dict]:
    """Fetch today's MLB events from The Odds API."""
    url = f"{config.ODDS_API_BASE}/sports/baseball_mlb/events"
    params = {"apiKey": config.ODDS_API_KEY}
    try:
        resp = httpx.get(url, params=params, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        log.error(f"Failed to fetch MLB events: {exc}")
        return []


def _fetch_event_market(event_id: str, markets: str) -> list[dict]:
    """Fetch all player prop markets for a specific event."""
    url = f"{config.ODDS_API_BASE}/sports/baseball_mlb/events/{event_id}/odds"
    params = {
        "apiKey": config.ODDS_API_KEY,
        "regions": "us",
        "markets": markets,
        "bookmakers": "draftkings",
        "oddsFormat": "american",
    }
    try:
        resp = httpx.get(url, params=params, headers=HEADERS, timeout=15)
        if resp.status_code == 429:
            log.warning("Odds API Rate Limited (429). Retrying later...")
            return []
        resp.raise_for_status()
        data = resp.json()
        return _parse_event_response(data)
    except Exception as exc:
        log.debug(f"Odds API fetch failed for event={event_id}: {exc}")
        return []


def _parse_event_response(event_data: dict) -> list[dict]:
    """Parse a single event response from The Odds API."""
    rows: list[dict] = []
    home_team = event_data.get("home_team", "")
    away_team = event_data.get("away_team", "")
    game_time = event_data.get("commence_time", "")

    bookmakers = event_data.get("bookmakers", [])
    dk = next((b for b in bookmakers if b.get("key") == "draftkings"), None)
    if not dk:
        return []

    for mkt in dk.get("markets", []):
        market_key = mkt.get("key", "")
        prop_label = _MARKET_LABEL_MAP.get(market_key, market_key)
        
        for outcome in mkt.get("outcomes", []):
            name = outcome.get("name", "")       # "Over" or "Under"
            description = outcome.get("description", "")  # player name
            point = outcome.get("point")          # the line
            price = outcome.get("price")          # American odds

            if not description or point is None:
                continue

            # Check if we already have a row for this player/prop/game
            existing = next(
                (r for r in rows if r["player_name"] == description
                 and r["prop_type"] == prop_label
                 and r["game_time"] == game_time),
                None
            )
            if existing:
                if name == "Over":
                    existing["over_odds"] = price
                elif name == "Under":
                    existing["under_odds"] = price
            else:
                row: dict = {
                    "player_name": description,
                    "prop_type": prop_label,
                    "line_score": float(point),
                    "over_odds": price if name == "Over" else None,
                    "under_odds": price if name == "Under" else None,
                    "home_team": home_team,
                    "away_team": away_team,
                    "game_time": game_time,
                    "source": "DraftKings",
                }
                rows.append(row)
    return rows


def get_draftkings_by_prop(prop_type: str) -> pd.DataFrame:
    """Filter DraftKings lines to a specific prop type."""
    df = get_draftkings_lines()
    if df.empty:
        return df
    mask = df["prop_type"].str.lower() == prop_type.lower()
    return df[mask].reset_index(drop=True)


def compare_lines(player_name: str, prop_type: str) -> dict:
    """
    Compare PrizePicks and DraftKings lines for a player/prop combo.
    Returns dict with both lines and any discrepancy.
    """
    from data.prizepicks_scraper import get_prizepicks_lines  # avoid circular at module level

    pp_df = get_prizepicks_lines()
    dk_df = get_draftkings_lines()

    result: dict = {"player": player_name, "prop": prop_type}

    # PrizePicks line
    if not pp_df.empty:
        pp_match = pp_df[
            (pp_df["player_name"].str.lower() == player_name.lower())
            & (pp_df["prop_type"].str.lower() == prop_type.lower())
        ]
        result["prizepicks_line"] = float(pp_match["line_score"].iloc[0]) if not pp_match.empty else None

    # DraftKings line
    if not dk_df.empty:
        dk_match = dk_df[
            (dk_df["player_name"].str.lower() == player_name.lower())
            & (dk_df["prop_type"].str.lower() == prop_type.lower())
        ]
        result["draftkings_line"] = float(dk_match["line_score"].iloc[0]) if not dk_match.empty else None

    # Discrepancy
    pp_line = result.get("prizepicks_line")
    dk_line = result.get("draftkings_line")
    if pp_line is not None and dk_line is not None:
        result["discrepancy"] = round(abs(pp_line - dk_line), 2)

    return result
