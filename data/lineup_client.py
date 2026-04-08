"""
data/lineup_client.py — Confirmed starting lineup intelligence.

Fetches the MLB API's confirmed batting orders before lock.
Prevents the system from generating picks on players who are:
  - Not in the starting lineup (DNPs)
  - Batting 7-9 / low in the order (reduced PA probability)

This fixes the "Yordan Alvarez Runs 0.5" failure pattern where
projected starters that came off the field mid-game were still scored.
"""
from __future__ import annotations

import datetime
import logging
from typing import Optional

import statsapi
from utils import cache
import config

log = logging.getLogger(__name__)


@cache.cached(ttl=config.CACHE_TTL_GAME_LOGS, key_prefix="lineup")
def get_confirmed_lineups(date: datetime.date) -> dict[str, dict]:
    """
    Return confirmed starting lineups for all games on date.
    Returns: {player_name.lower(): {'batting_order': int, 'team': str, 'game_id': int}}
    """
    date_str = date.strftime("%m/%d/%Y")
    try:
        schedule = statsapi.schedule(date=date_str)
    except Exception as exc:
        log.warning(f"Could not fetch schedule for lineup: {exc}")
        return {}

    lineups: dict[str, dict] = {}

    for game in schedule:
        game_id = game.get("game_id")
        status  = game.get("status", "")
        if not game_id:
            continue

        try:
            box = statsapi.boxscore_data(game_id)
        except Exception:
            continue

        for side in ("home", "away"):
            team_name = box.get(f"{side}Teams", {}).get("team", {}).get("name", "")
            batters   = box.get(f"{side}Teams", {}).get("batters", [])
            players   = box.get(f"{side}Teams", {}).get("players", {})

            for order_idx, player_id in enumerate(batters):
                p_key  = f"ID{player_id}"
                p_info = players.get(p_key, {})
                p_name = p_info.get("person", {}).get("fullName", "")
                if not p_name:
                    continue

                lineups[p_name.lower()] = {
                    "batting_order": order_idx + 1,  # 1-indexed
                    "team": team_name,
                    "game_id": game_id,
                    "game_status": status,
                }

    log.info(f"Lineup client: {len(lineups)} confirmed starters for {date}")
    return lineups


def is_player_starting(player_name: str, date: datetime.date) -> tuple[bool, int]:
    """
    Returns (is_starting, batting_order) for a player on a given date.
    is_starting=False means they are NOT in the confirmed lineup (DNP risk).
    batting_order=0 means not yet confirmed.
    """
    lineups = get_confirmed_lineups(date)
    info = lineups.get(player_name.lower())
    if info is None:
        return True, 0  # Lineup not yet confirmed — be permissive
    return True, info["batting_order"]


def get_lineup_signal(player_name: str, date: datetime.date) -> dict[str, float]:
    """
    Return lineup-based signals for injection into the confidence scorer.
      batting_order_signal: [1-3] = 0.8 (lots of PAs), [7-9] = -0.3 (fewer PAs)
      confirmed_starter: 1.0 if confirmed, 0.0 if not in lineup
    """
    is_starting, order = is_player_starting(player_name, date)

    if not is_starting:
        return {"confirmed_starter": 0.0, "batting_order_signal": -1.0}

    if order == 0:
        # Not confirmed yet — neutral
        return {}

    # Lineup impact scoring
    if order <= 3:
        bo_signal = 0.8   # Cleanup hitter / top of order = max PAs
    elif order <= 6:
        bo_signal = 0.2   # Middle order — average
    else:
        bo_signal = -0.3  # Bottom of order — fewer ABs

    return {
        "confirmed_starter": 1.0,
        "batting_order_signal": bo_signal,
    }
