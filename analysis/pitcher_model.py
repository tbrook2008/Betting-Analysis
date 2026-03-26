"""
analysis/pitcher_model.py — Signal generator for Pitcher Strikeout props.

Signals:
  - k_per_9:            Strikeouts per 9 innings (season)
  - k_pct:              Strikeout % of batters faced
  - whiff_rate:         Swinging strike % (Statcast)
  - xfip:               Expected FIP (lower = better pitcher)
  - opp_team_k_rate:    Opposing team's K% over last 14 days
  - home_away_split:    Pitcher's K/9 at home vs away (if applicable)
  - days_rest:          Days since last start (fatigue check)
"""
from __future__ import annotations

import datetime
from typing import Optional

from data import mlb_client as mlb
from utils.logger import get_logger

log = get_logger(__name__)


def generate_pitcher_k_signals(
    pitcher_name: str,
    opp_team_abbrev: str,
    is_home: bool = True,
    pitcher_id: Optional[int] = None,
) -> dict[str, float]:
    """
    Generate all signals for the Pitcher Strikeouts model.

    Args:
        pitcher_name:       Starting pitcher's full name
        opp_team_abbrev:    Opposing team abbreviation (e.g. "NYY", "LAD")
        is_home:            True if pitcher is the home starter
        pitcher_id:         MLB Stats player ID (optional)

    Returns:
        Dict of signal_name → raw numeric value.
    """
    signals: dict[str, float] = {}

    # ── 1. Resolve pitcher ID ────────────────────────────────────────────────
    if pitcher_id is None:
        pitcher_id = mlb.get_player_id(pitcher_name)

    # ── 2. FanGraphs / Statcast pitcher stats ────────────────────────────────
    sc = mlb.get_statcast_pitcher_stats(pitcher_name)
    if sc:
        if sc.get("k_per_9"):
            signals["k_per_9"] = float(sc["k_per_9"])
        if sc.get("k_pct"):
            signals["k_pct"] = float(sc["k_pct"])
        if sc.get("whiff_rate"):
            signals["whiff_rate"] = float(sc["whiff_rate"])
        if sc.get("xfip"):
            signals["xfip"] = float(sc["xfip"])
        if sc.get("hr_per_9"):
            signals["hr_per_9"] = float(sc["hr_per_9"])

    # ── 3. Fallback: MLB Stats API season stats ──────────────────────────────
    if pitcher_id and not sc:
        p_stats = mlb.get_season_pitching_stats(pitcher_id)
        so = float(p_stats.get("strikeOuts", 0) or 0)
        ip = float(p_stats.get("inningsPitched", 1) or 1)
        bf = float(p_stats.get("battersFaced", 1) or 1)
        if ip > 0:
            signals["k_per_9"] = round(so / ip * 9, 2)
        if bf > 0:
            signals["k_pct"] = round(so / bf * 100, 1)

    # ── 4. Opposing team K rate ──────────────────────────────────────────────
    opp_k_rate = mlb.get_team_strikeout_rate(opp_team_abbrev)
    if opp_k_rate:
        signals["opp_team_k_rate"] = opp_k_rate

    # ── 5. Home/Away split ───────────────────────────────────────────────────
    if pitcher_id:
        home_k9, away_k9 = _get_home_away_k9(pitcher_id)
        current_k9 = home_k9 if is_home else away_k9
        if current_k9 is not None:
            signals["home_away_split"] = current_k9

    # ── 6. Days rest ─────────────────────────────────────────────────────────
    if pitcher_id:
        days_rest = _get_days_rest(pitcher_id)
        if days_rest is not None:
            # 4-5 days ideal; flag if < 4 (fatigue) or > 7 (rust)
            signals["days_rest"] = float(days_rest)

    log.debug(f"Pitcher K signals for {pitcher_name}: {signals}")
    return signals


# ─────────────────────────────────────────────────────────────────────────────
# Private helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_home_away_k9(pitcher_id: int) -> tuple[Optional[float], Optional[float]]:
    """Return (home_k9, away_k9) from season split data."""
    try:
        raw = mlb.statsapi.player_stat_data(pitcher_id, group="pitching", type="statSplits")
        splits = raw.get("stats", [{}])[0].get("splits", [])
        home_k9 = away_k9 = None
        for s in splits:
            code = s.get("split", {}).get("code", "")
            stat = s.get("stat", {})
            so = float(stat.get("strikeOuts", 0) or 0)
            ip = float(stat.get("inningsPitched", 1) or 1)
            k9 = round(so / ip * 9, 2) if ip > 0 else 0
            if code == "h":
                home_k9 = k9
            elif code == "a":
                away_k9 = k9
        return home_k9, away_k9
    except Exception as exc:
        log.debug(f"Home/away split fetch failed for {pitcher_id}: {exc}")
        return None, None


def _get_days_rest(pitcher_id: int) -> Optional[int]:
    """Return number of days since pitcher's last start."""
    try:
        logs = mlb.get_pitcher_game_logs(pitcher_id, last_n=10)
        if logs.empty or "date" not in logs.columns:
            return None
        # Find last start (IP > 0 as a proxy)
        started = logs[logs["IP"] > 0]
        if started.empty:
            return None
        last_date_str = started.iloc[-1]["date"]
        last_date = datetime.date.fromisoformat(str(last_date_str)[:10])
        return (datetime.date.today() - last_date).days
    except Exception as exc:
        log.debug(f"Days rest fetch failed for {pitcher_id}: {exc}")
        return None
