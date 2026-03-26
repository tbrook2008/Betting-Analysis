"""
analysis/hr_model.py — Signal generator for Home Run props.

Signals:
  - barrel_pct:       Statcast barrel rate
  - hard_hit_pct:     Hard-hit % (exit velo ≥ 95 mph)
  - fly_ball_pct:     Fly ball launch type %
  - opp_hr_per_9:     Opposing pitcher HR/9 (more prone → positive signal)
  - park_hr_factor:   Ballpark HR factor
  - wind_boost:       Wind speed/direction proxy (stub; uses 0.0 by default)
"""
from __future__ import annotations

from typing import Optional

from data import mlb_client as mlb
from utils.logger import get_logger

log = get_logger(__name__)


def generate_hr_signals(
    player_name: str,
    opp_pitcher_name: str,
    venue: str,
    wind_speed_mph: float = 0.0,
    wind_toward_of: bool = False,   # True = blowing out to outfield (positive)
    player_id: Optional[int] = None,
    opp_pitcher_id: Optional[int] = None,
) -> dict[str, float]:
    """
    Generate all signals for the Home Run model.

    Args:
        player_name:      Batter full name
        opp_pitcher_name: Opposing starter full name
        venue:            Ballpark name
        wind_speed_mph:   Current wind speed (0 = unknown/calm)
        wind_toward_of:   True if wind is blowing toward outfield
        player_id:        MLB Stats player ID (optional)
        opp_pitcher_id:   MLB Stats pitcher ID (optional)

    Returns:
        Dict of signal_name → raw numeric value.
    """
    signals: dict[str, float] = {}

    # ── 1. Resolve IDs ───────────────────────────────────────────────────────
    if player_id is None:
        player_id = mlb.get_player_id(player_name)
    if opp_pitcher_id is None:
        opp_pitcher_id = mlb.get_player_id(opp_pitcher_name)

    # ── 2. Statcast batter — barrel%, hard hit%, fly ball% ───────────────────
    sc_summary = mlb.get_statcast_batter_stats(player_name)
    
    # Lazily fetch detail only if we need it (e.g. for Fly Ball% or if summary is missing)
    sc_detail = {}
    if not sc_summary or "barrel_pct" not in sc_summary:
        sc_detail = mlb.get_statcast_batter_detail(player_name)

    # Prefer summary (season-wide stats) over detail (recent sample) for stable rates
    barrel_pct = sc_summary.get("barrel_pct") or sc_detail.get("barrel_pct", 0.0)
    hard_hit_pct = sc_summary.get("hard_hit_pct") or sc_detail.get("hard_hit_pct", 0.0)
    
    # Fly ball % logic: use detail if summary is missing it
    fly_ball_pct = sc_detail.get("fly_ball_pct", 0.0)

    if barrel_pct:
        signals["barrel_pct"] = float(barrel_pct)
    if hard_hit_pct:
        signals["hard_hit_pct"] = float(hard_hit_pct)
    if fly_ball_pct:
        signals["fly_ball_pct"] = float(fly_ball_pct)

    # ── 3. Recent HR trend from game logs ────────────────────────────────────
    if player_id:
        logs = mlb.get_batter_game_logs(player_id, last_n=30)
        if not logs.empty:
            hr_last_30 = int(logs.tail(30)["HR"].sum())
            hr_last_14 = int(logs.tail(14)["HR"].sum())
            # Annualized rate proxy: HR / PA * 600
            ab_30 = int(logs.tail(30)["AB"].sum())
            if ab_30 > 0:
                hr_rate = hr_last_30 / ab_30
                signals["hr_rate_30d"] = round(hr_rate * 100, 2)  # HR% of AB

    # ── 4. Opposing pitcher HR/9 ─────────────────────────────────────────────
    if opp_pitcher_name:
        p_sc = mlb.get_statcast_pitcher_stats(opp_pitcher_name)
        if p_sc.get("hr_per_9"):
            signals["opp_hr_per_9"] = float(p_sc["hr_per_9"])
        elif opp_pitcher_id:
            p_stats = mlb.get_season_pitching_stats(opp_pitcher_id)
            hr = float(p_stats.get("homeRuns", 0) or 0)
            ip = float(p_stats.get("inningsPitched", 1) or 1)
            signals["opp_hr_per_9"] = round((hr / ip) * 9, 2) if ip > 0 else 1.0

    # ── 5. Park HR factor ────────────────────────────────────────────────────
    signals["park_hr_factor"] = mlb.get_park_hr_factor(venue)

    # ── 6. Wind boost ────────────────────────────────────────────────────────
    # Simple linear boost: 10 mph out = +0.05 factor, 10 mph in = -0.05
    if wind_speed_mph > 0:
        direction_mult = 1.0 if wind_toward_of else -1.0
        signals["wind_boost"] = round(direction_mult * min(wind_speed_mph / 20.0, 0.15), 3)
    else:
        signals["wind_boost"] = 0.0

    log.debug(f"HR signals for {player_name}: {signals}")
    return signals
