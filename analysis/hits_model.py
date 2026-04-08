"""
analysis/hits_model.py — Signal generator for Hits & Total Bases props.

Signals (all normalized to [-1, +1] by confidence_scorer):
  - rolling_avg_7/14/30:   recent batting average trend
  - handedness_split:      batter AVG vs pitcher handedness
  - park_hit_factor:       ballpark run/hit factor
  - opp_pitcher_k_pct:     opposing pitcher K% (high → negative for hitters)
"""
from __future__ import annotations

from typing import Optional

import pandas as pd
import numpy as np

from data import mlb_client as mlb
from utils.logger import get_logger

log = get_logger(__name__)


def generate_hits_signals(
    player_name: str,
    opp_pitcher_name: str,
    venue: str,
    pitcher_throws: str = "R",    # "L" or "R"
    player_id: Optional[int] = None,
    opp_pitcher_id: Optional[int] = None,
) -> dict[str, float]:
    """
    Generate all signals for the Hits / Total Bases model.

    Args:
        player_name:      Batter's full name
        opp_pitcher_name: Opposing starter's full name
        venue:            Stadium name (for park factor lookup)
        pitcher_throws:   "L" or "R" — opposing pitcher handedness
        player_id:        MLB Stats player ID (optional, will look up if omitted)
        opp_pitcher_id:   MLB Stats pitcher ID (optional)

    Returns:
        Dict of signal_name → raw numeric value (not yet normalized).
        Missing / unavailable signals are omitted.
    """
    signals: dict[str, float] = {}

    # ── 1. Resolve player IDs ────────────────────────────────────────────────
    if player_id is None:
        player_id = mlb.get_player_id(player_name)
    if opp_pitcher_id is None:
        opp_pitcher_id = mlb.get_player_id(opp_pitcher_name)

    # ── 2. Rolling batting average and L10 Stability from game logs ──────────
    if player_id:
        logs = mlb.get_batter_game_logs(player_id, last_n=30)
        if not logs.empty:
            signals.update(_rolling_avg_signals(logs))
            
            # Stability check (hit in last 10 games)
            # Default line for hits is usually 0.5, so we check H > 0
            l10 = logs.tail(10)
            hits_in_l10 = (l10["H"] > 0).sum()
            signals["last_10_hit_rate"] = float(hits_in_l10 / 10.0)

    # ── 3. Handedness split ──────────────────────────────────────────────────
    if player_id:
        splits = mlb.get_batter_splits(player_id)
        split_key = "vs_L" if pitcher_throws.upper() == "L" else "vs_R"
        split_avg = _safe_float(splits.get(split_key, {}).get("avg"))
        if split_avg is not None:
            signals["handedness_split"] = split_avg

    # ── 4. Park hit factor (use run factor as proxy) ─────────────────────────
    park_factor = mlb.get_park_run_factor(venue)
    signals["park_hit_factor"] = park_factor

    # ── 5. Opposing pitcher K% (inverse signal — high K% → fewer hits) ──────
    if opp_pitcher_id:
        p_stats = mlb.get_season_pitching_stats(opp_pitcher_id)
        so = float(p_stats.get("strikeOuts", 0) or 0)
        bf = float(p_stats.get("battersFaced", 1) or 1)
        opp_k_pct = (so / bf * 100) if bf > 0 else 0
        signals["opp_pitcher_k_pct"] = opp_k_pct

    # Supplement with Statcast pitcher K%
    if opp_pitcher_name:
        sc = mlb.get_statcast_pitcher_stats(opp_pitcher_name)
        if sc.get("k_pct"):
            signals["opp_pitcher_k_pct"] = sc["k_pct"]

    # ── 6. [v5.2] Weather signals ─────────────────────────────────────────────
    try:
        from data.weather_client import get_weather_signals
        wx = get_weather_signals(venue)
        if wx.get("wind_out_boost"):
            signals["wind_out_boost"] = wx["wind_out_boost"]
        if wx.get("wind_in_penalty"):
            signals["wind_in_penalty"] = -wx["wind_in_penalty"]  # inverted; penalty
        if wx.get("temp_boost"):
            signals["temp_boost"] = wx["temp_boost"]
    except Exception as exc:
        log.debug(f"Weather signals skipped: {exc}")

    # ── 7. [v5.2] Lineup / batting-order signals ──────────────────────────────
    try:
        import datetime
        from data.lineup_client import get_lineup_signal
        lineup_sigs = get_lineup_signal(player_name, datetime.date.today())
        signals.update(lineup_sigs)
    except Exception as exc:
        log.debug(f"Lineup signals skipped: {exc}")

    log.debug(f"Hits signals for {player_name}: {signals}")
    return signals


def generate_total_bases_signals(
    player_name: str,
    opp_pitcher_name: str,
    venue: str,
    pitcher_throws: str = "R",
    player_id: Optional[int] = None,
    opp_pitcher_id: Optional[int] = None,
) -> dict[str, float]:
    """
    Signals for Total Bases prop. Extends hits signals with power metrics.
    """
    signals = generate_hits_signals(
        player_name, opp_pitcher_name, venue,
        pitcher_throws, player_id, opp_pitcher_id
    )

    # ── [NEW] Add Statcast to HITS/TB ────────────────────────────────────────
    sc = mlb.get_statcast_batter_stats(player_name)
    if sc:
        if sc.get("hard_hit_pct"):
            signals["hard_hit_pct"] = sc["hard_hit_pct"]
            
        if sc.get("barrel_pct"):
            signals["barrel_pct"] = sc["barrel_pct"]

        # Only fetch detail if we really want fly_ball_pct (expensive)
        detail = mlb.get_statcast_batter_detail(player_name)
        if detail.get("fly_ball_pct"):
            signals["fly_ball_pct"] = detail["fly_ball_pct"]

    return signals


# ─────────────────────────────────────────────────────────────────────────────
# Private helpers
# ─────────────────────────────────────────────────────────────────────────────

def _rolling_avg_signals(logs: pd.DataFrame) -> dict[str, float]:
    """Compute 7/14/30-day rolling hit average from game log df."""
    signals: dict[str, float] = {}
    for window, key in [(7, "rolling_avg_7"), (14, "rolling_avg_14"), (30, "rolling_avg_30")]:
        subset = logs.tail(window)
        total_h = subset["H"].sum()
        total_ab = subset["AB"].sum()
        if total_ab > 0:
            signals[key] = round(total_h / total_ab, 3)
    return signals


def _safe_float(val) -> Optional[float]:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None
