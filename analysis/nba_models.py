"""
analysis/nba_models.py — Generates signals for NBA player props (Points, Rebounds, Assists, PRA).
"""
from __future__ import annotations

import pandas as pd
from data import nba_client
from utils.logger import get_logger

log = get_logger(__name__)

def generate_nba_signals(player_name: str, prop_type: str, line: float) -> dict:
    """
    Generate confidence signals for NBA props based on trailing game logs.
    """
    signals = {
        "l5_hit_rate": 0.0,
        "l15_hit_rate": 0.0,
        "season_avg": 0.0,
        "projected_value": 0.0, # Baseline projection
    }

    # 1. Look up Player
    player_id = nba_client.get_player_id(player_name)
    if not player_id:
        return signals

    # 2. Get historical game logs
    logs = nba_client.get_player_game_logs(player_id, last_n=15)
    season_stats = nba_client.get_season_stats(player_id)
    
    if logs.empty:
        return signals

    # 3. Determine stat column mapping
    prop_lower = prop_type.lower()
    if 'pts+rebs+asts' in prop_lower or 'pra' in prop_lower:
        logs['stat'] = logs['PTS'] + logs['REB'] + logs['AST']
        signals['season_avg'] = float(season_stats.get('pts', 0)) + float(season_stats.get('reb', 0)) + float(season_stats.get('ast', 0))
    elif 'pts+rebs' in prop_lower:
        logs['stat'] = logs['PTS'] + logs['REB']
        signals['season_avg'] = float(season_stats.get('pts', 0)) + float(season_stats.get('reb', 0))
    elif 'pts+asts' in prop_lower:
        logs['stat'] = logs['PTS'] + logs['AST']
        signals['season_avg'] = float(season_stats.get('pts', 0)) + float(season_stats.get('ast', 0))
    elif 'rebs+asts' in prop_lower:
        logs['stat'] = logs['REB'] + logs['AST']
        signals['season_avg'] = float(season_stats.get('reb', 0)) + float(season_stats.get('ast', 0))
    elif 'point' in prop_lower or 'pts' in prop_lower:
        logs['stat'] = logs['PTS']
        signals['season_avg'] = float(season_stats.get('pts', 0))
    elif 'rebound' in prop_lower or 'reb' in prop_lower:
        logs['stat'] = logs['REB']
        signals['season_avg'] = float(season_stats.get('reb', 0))
    elif 'assist' in prop_lower or 'ast' in prop_lower:
        logs['stat'] = logs['AST']
        signals['season_avg'] = float(season_stats.get('ast', 0))
    else:
        # Unsupported prop type for now (e.g., 3-PT, Steals, Blocks)
        return signals

    # 4. Calculate Hit Rates
    l5_logs = logs.tail(5)
    
    if not l5_logs.empty:
        signals['l5_hit_rate'] = (l5_logs['stat'] > line).mean()
    if not logs.empty:
        signals['l15_hit_rate'] = (logs['stat'] > line).mean()

    # 5. Simple Projection (Weighted average of recent momentum and season baseline)
    l5_avg = l5_logs['stat'].mean() if not l5_logs.empty else 0
    l15_avg = logs['stat'].mean() if not logs.empty else 0
    
    # 50% L5, 30% L15, 20% Season Avg
    signals['projected_value'] = (l5_avg * 0.5) + (l15_avg * 0.3) + (signals['season_avg'] * 0.2)
    
    # Add over/under edge heuristic
    signals['is_over_value'] = signals['projected_value'] > line

    return signals
