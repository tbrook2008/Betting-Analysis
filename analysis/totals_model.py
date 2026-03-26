"""
analysis/totals_model.py — Signal generator for Game Total (O/U) props.

Signals:
  - team1_runs_per_game:  Home team avg runs/game (last 14)
  - team2_runs_per_game:  Away team avg runs/game (last 14)
  - starter1_xfip:        Home starter xFIP (lower = run suppression)
  - starter2_xfip:        Away starter xFIP
  - park_run_factor:      Ballpark run factor
  - wind_factor:          Wind speed impact on run scoring
  - bullpen_fatigue:      Both teams' bullpen fatigue (tired pen → more runs)
"""
from __future__ import annotations

from typing import Optional

from data import mlb_client as mlb
from utils.logger import get_logger

log = get_logger(__name__)

# League-average xFIP baseline (used if pitcher data unavailable)
_LEAGUE_AVG_XFIP = 4.20


def generate_totals_signals(
    home_team_id: int,
    away_team_id: int,
    home_starter_name: str,
    away_starter_name: str,
    venue: str,
    wind_speed_mph: float = 0.0,
    wind_is_favorable: bool = True,  # True = blowing to outfield (more runs)
    home_starter_id: Optional[int] = None,
    away_starter_id: Optional[int] = None,
) -> dict[str, float]:
    """
    Generate all signals for the Game Totals model.

    Args:
        home_team_id:        MLB Stats team ID for home team
        away_team_id:        MLB Stats team ID for away team
        home_starter_name:   Home starting pitcher full name
        away_starter_name:   Away starting pitcher full name
        venue:               Ballpark name
        wind_speed_mph:      Wind speed (0 = calm/unknown)
        wind_is_favorable:   True = blowing toward OF (boosts scoring)
        home_starter_id:     MLB Stats pitcher ID (optional)
        away_starter_id:     MLB Stats pitcher ID (optional)

    Returns:
        Dict of signal_name → raw numeric value.
    """
    signals: dict[str, float] = {}

    # ── 1. Team run production (last 14 games) ───────────────────────────────
    home_rpg = mlb.get_team_runs_per_game(home_team_id, last_n=14)
    away_rpg = mlb.get_team_runs_per_game(away_team_id, last_n=14)
    signals["team1_runs_per_game"] = home_rpg
    signals["team2_runs_per_game"] = away_rpg

    # ── 2. Starters xFIP ────────────────────────────────────────────────────
    home_xfip = _get_starter_xfip(home_starter_name, home_starter_id)
    away_xfip = _get_starter_xfip(away_starter_name, away_starter_id)
    signals["starter1_xfip"] = home_xfip
    signals["starter2_xfip"] = away_xfip

    # ── 3. Park run factor ───────────────────────────────────────────────────
    signals["park_run_factor"] = mlb.get_park_run_factor(venue)

    # ── 4. Wind factor ───────────────────────────────────────────────────────
    # Mild boost/penalty: 10 mph blowing out ≈ +0.3 runs, in ≈ -0.3 runs
    if wind_speed_mph > 0:
        direction = 1.0 if wind_is_favorable else -1.0
        # Scale: max effect at 20+ mph
        wind_effect = direction * min(wind_speed_mph / 20.0, 1.0) * 0.5
        signals["wind_factor"] = round(wind_effect, 3)
    else:
        signals["wind_factor"] = 0.0

    # ── 5. Bullpen fatigue ───────────────────────────────────────────────────
    home_fatigue = mlb.get_bullpen_fatigue(home_team_id, days=3)
    away_fatigue = mlb.get_bullpen_fatigue(away_team_id, days=3)
    # Average combined fatigue (more fatigue → more runs given up late)
    signals["bullpen_fatigue"] = round((home_fatigue + away_fatigue) / 2, 1)

    log.debug(
        f"Totals signals for {home_starter_name} vs {away_starter_name} "
        f"at {venue}: {signals}"
    )
    return signals


def project_total_runs(signals: dict[str, float]) -> float:
    """
    Produce a projected run total from the signals dict.
    Uses a simple additive model calibrated to MLB averages (~9 runs/game).

    This is used by the confidence scorer to compare against the posted O/U line.
    """
    # Base: sum of both teams' runs/game
    base = signals.get("team1_runs_per_game", 4.5) + signals.get("team2_runs_per_game", 4.5)

    # Pitcher quality adjustment: deviation from league avg xFIP (4.20)
    s1_xfip = signals.get("starter1_xfip", _LEAGUE_AVG_XFIP)
    s2_xfip = signals.get("starter2_xfip", _LEAGUE_AVG_XFIP)
    # Each 0.5 ERA of xFIP above league avg ≈ +0.5 runs allowed
    pitcher_adjustment = ((s1_xfip - _LEAGUE_AVG_XFIP) + (s2_xfip - _LEAGUE_AVG_XFIP)) * 0.8

    # Park adjustment
    park_factor = signals.get("park_run_factor", 1.0)
    # A 1.10 park factor means 10% more runs
    park_adjustment = base * (park_factor - 1.0)

    # Wind
    wind = signals.get("wind_factor", 0.0)

    # Bullpen fatigue: league avg bullpen gives ~3–4 innings; fatigue adds runs
    fatigue = signals.get("bullpen_fatigue", 0.0)
    fatigue_adjustment = min(fatigue / 10.0, 1.0)  # cap at +1 run

    projected = base + pitcher_adjustment + park_adjustment + wind + fatigue_adjustment
    return round(max(projected, 3.0), 2)  # floor at 3 runs


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_starter_xfip(pitcher_name: str, pitcher_id: Optional[int] = None) -> float:
    """Return pitcher xFIP, falling back to league average."""
    if pitcher_name and pitcher_name.lower() not in ("tbd", "tbp", ""):
        sc = mlb.get_statcast_pitcher_stats(pitcher_name)
        xfip = sc.get("xfip")
        if xfip:
            return float(xfip)
    # MLB Stats API fallback: use ERA as rough proxy
    if pitcher_id:
        p_stats = mlb.get_season_pitching_stats(pitcher_id)
        era = float(p_stats.get("era", 0) or 0)
        if era > 0:
            return era
    return _LEAGUE_AVG_XFIP
