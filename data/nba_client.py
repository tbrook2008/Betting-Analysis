"""
data/nba_client.py — NBA API wrapper for player stats and game logs.
"""
from __future__ import annotations

from typing import Optional
import datetime
import pandas as pd
from functools import lru_cache

from nba_api.stats.static import players
from nba_api.stats.endpoints import playergamelog, commonplayerinfo, teamgamelog
from nba_api.stats.library.parameters import SeasonAll

import config
from utils.cache import cached
from utils.logger import get_logger

log = get_logger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Player Lookups
# ─────────────────────────────────────────────────────────────────────────────

@cached(ttl=config.CACHE_TTL_GAME_LOGS, key_prefix="nba_player_lookup")
def get_player_id(name: str) -> Optional[int]:
    """Look up NBA player ID by full name."""
    nba_players = players.find_players_by_full_name(name)
    if not nba_players:
        log.warning(f"NBA Player not found: {name}")
        return None
    
    # Simple match: just take the first active if multiple, or the first one
    active_players = [p for p in nba_players if p.get('is_active')]
    if active_players:
        return active_players[0]['id']
    return nba_players[0]['id']


# ─────────────────────────────────────────────────────────────────────────────
# Game Logs & Stats
# ─────────────────────────────────────────────────────────────────────────────

@cached(ttl=config.CACHE_TTL_GAME_LOGS, key_prefix="nba_game_logs")
def get_player_game_logs(player_id: int, last_n: int = 15) -> pd.DataFrame:
    """
    Fetch recent game logs for an NBA player.
    Returns DataFrame with pts, reb, ast.
    """
    try:
        log_fetcher = playergamelog.PlayerGameLog(player_id=player_id)
        df = log_fetcher.get_data_frames()[0]
        if df.empty:
            return df
        
        # Sort by date ascending (nba_api returns newest first)
        df = df.iloc[::-1].reset_index(drop=True)
        return df.tail(last_n)
    except Exception as e:
        log.error(f"Failed to fetch NBA logs for {player_id}: {e}")
        return pd.DataFrame()

@cached(ttl=config.CACHE_TTL_GAME_LOGS, key_prefix="nba_season_stats")
def get_season_stats(player_id: int) -> dict:
    """Fetch current-season aggregate stats for a player."""
    try:
        info = commonplayerinfo.CommonPlayerInfo(player_id=player_id)
        df = info.get_data_frames()[1] # HeadlineStats
        if df.empty:
            return {}
        
        return {
            "pts": df['PTS'].iloc[0] if 'PTS' in df.columns else 0.0,
            "reb": df['REB'].iloc[0] if 'REB' in df.columns else 0.0,
            "ast": df['AST'].iloc[0] if 'AST' in df.columns else 0.0,
        }
    except Exception as e:
        log.error(f"Failed to fetch season stats for {player_id}: {e}")
        return {}

@cached(ttl=config.CACHE_TTL_GAME_LOGS, key_prefix="nba_stat_resolution")
def get_player_stat_on_date(player_name: str, date: datetime.date, category: str) -> Optional[float]:
    """
    Resolve a specific stat for a player on a target date.
    Used for grading/performance resolution.
    """
    player_id = get_player_id(player_name)
    if not player_id:
        return None

    # Fetch logs (last 50 to be safe for late-season resolution)
    logs = get_player_game_logs(player_id, last_n=50)
    if logs.empty:
        return None

    # Date format in nba_api is 'Apr 17, 2026'
    date_str = date.strftime("%b %d, %Y")
    
    # Filter for the specific game
    game_row = logs[logs['GAME_DATE'] == date_str]
    if game_row.empty:
        log.warning(f"No game found for {player_name} on {date_str}")
        return None

    row = game_row.iloc[0]
    cat = category.lower()
    
    # Support Combo Stats
    if 'pts+rebs+asts' in cat or 'pra' in cat:
        return float(row['PTS'] + row['REB'] + row['AST'])
    if 'pts+rebs' in cat:
        return float(row['PTS'] + row['REB'])
    if 'pts+asts' in cat:
        return float(row['PTS'] + row['AST'])
    if 'rebs+asts' in cat:
        return float(row['REB'] + row['AST'])
    
    # Support Single Stats
    mapping = {
        'points': 'PTS', 'pts': 'PTS',
        'rebounds': 'REB', 'reb': 'REB',
        'assists': 'AST', 'ast': 'AST',
        'steals': 'STL', 'stl': 'STL',
        'blocked shots': 'BLK', 'blk': 'BLK',
        'turnovers': 'TOV',
    }
    
    stat_col = mapping.get(cat)
    if stat_col and stat_col in row:
        return float(row[stat_col])
        
    return None
