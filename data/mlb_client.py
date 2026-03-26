"""
data/mlb_client.py — MLB Stats API + pybaseball (Statcast/FanGraphs) wrappers.

All functions are cached via utils.cache.cached() to avoid hammering APIs.
All data is returned as pandas DataFrames or plain Python dicts.
"""
from __future__ import annotations

import datetime
from typing import Optional

import pandas as pd
import statsapi
import pybaseball as pb

import config
from utils.cache import cached
from utils.logger import get_logger

log = get_logger(__name__)

# Silence pybaseball's progress bar
pb.cache.enable()


# ─────────────────────────────────────────────────────────────────────────────
# Schedule
# ─────────────────────────────────────────────────────────────────────────────

@cached(ttl=config.CACHE_TTL_SCHEDULE, key_prefix="schedule")
def get_schedule(date: datetime.date | str | None = None) -> list[dict]:
    """
    Return today's (or given date's) MLB schedule as a list of game dicts.

    Each dict has keys: game_id, status, home_team, away_team, game_datetime,
    venue, home_pitcher_id, away_pitcher_id (may be None if not announced).
    """
    if date is None:
        date = datetime.date.today()
    date_str = date.strftime("%m/%d/%Y") if isinstance(date, datetime.date) else date

    raw = statsapi.schedule(date=date_str)
    games = []
    for g in raw:
        games.append({
            "game_id": g.get("game_id"),
            "status": g.get("status"),
            "home_team": g.get("home_name"),
            "away_team": g.get("away_name"),
            "game_datetime": g.get("game_datetime"),
            "venue": g.get("venue_name"),
            "home_pitcher_id": g.get("home_probable_pitcher_id"),
            "away_pitcher_id": g.get("away_probable_pitcher_id"),
            "home_pitcher_name": g.get("home_probable_pitcher", "TBD"),
            "away_pitcher_name": g.get("away_probable_pitcher", "TBD"),
        })
    log.info(f"Fetched {len(games)} games for {date_str}")
    return games


# ─────────────────────────────────────────────────────────────────────────────
# Player Lookups
# ─────────────────────────────────────────────────────────────────────────────

@cached(ttl=config.CACHE_TTL_SCHEDULE, key_prefix="player_lookup")
def get_player_id(name: str) -> Optional[int]:
    """Look up MLB player ID by full name. Returns None if not found."""
    results = statsapi.lookup_player(name)
    if not results:
        log.warning(f"Player not found: {name}")
        return None
    return results[0]["id"]


@cached(ttl=config.CACHE_TTL_SCHEDULE, key_prefix="player_info")
def get_player_info(player_id: int) -> dict:
    """Return basic player info dict (name, position, team, bats, throws)."""
    raw = statsapi.player_stat_data(player_id, group="hitting", type="season")
    info = raw.get("stats", [{}])[0] if raw.get("stats") else {}
    return {
        "id": player_id,
        "full_name": raw.get("full_name", ""),
        "position": raw.get("position", ""),
        "current_team": raw.get("current_team", ""),
        **info,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Game Logs (rolling)
# ─────────────────────────────────────────────────────────────────────────────

@cached(ttl=config.CACHE_TTL_GAME_LOGS, key_prefix="batter_logs")
def get_batter_game_logs(player_id: int, last_n: int = 30) -> pd.DataFrame:
    """
    Return last N game logs for a batter.
    Columns: date, H, AB, HR, RBI, BB, SO, AVG
    """
    raw = statsapi.player_stat_data(
        player_id, group="hitting", type="gameLog"
    )
    stats = raw.get("stats", [])
    if not stats:
        log.warning(f"No hitting stats found for player_id={player_id}")
        return pd.DataFrame()
    splits = stats[0].get("splits", [])
    rows = []
    for s in splits[-last_n:]:
        stat = s.get("stat", {})
        rows.append({
            "date": s.get("date"),
            "H": int(stat.get("hits", 0)),
            "AB": int(stat.get("atBats", 0)),
            "HR": int(stat.get("homeRuns", 0)),
            "RBI": int(stat.get("rbi", 0)),
            "BB": int(stat.get("baseOnBalls", 0)),
            "SO": int(stat.get("strikeOuts", 0)),
            "AVG": float(stat.get("avg", 0) or 0),
        })
    df = pd.DataFrame(rows)
    if df.empty:
        log.warning(f"No hit logs for player_id={player_id}")
    return df


@cached(ttl=config.CACHE_TTL_GAME_LOGS, key_prefix="pitcher_logs")
def get_pitcher_game_logs(player_id: int, last_n: int = 30) -> pd.DataFrame:
    """
    Return last N game logs for a pitcher.
    Columns: date, IP, H, ER, BB, SO, HR
    """
    raw = statsapi.player_stat_data(
        player_id, group="pitching", type="gameLog"
    )
    stats = raw.get("stats", [])
    if not stats:
        log.warning(f"No pitching stats found for player_id={player_id}")
        return pd.DataFrame()
    splits = stats[0].get("splits", [])
    rows = []
    for s in splits[-last_n:]:
        stat = s.get("stat", {})
        rows.append({
            "date": s.get("date"),
            "IP": float(stat.get("inningsPitched", 0) or 0),
            "H": int(stat.get("hits", 0)),
            "ER": int(stat.get("earnedRuns", 0)),
            "BB": int(stat.get("baseOnBalls", 0)),
            "SO": int(stat.get("strikeOuts", 0)),
            "HR": int(stat.get("homeRuns", 0)),
        })
    df = pd.DataFrame(rows)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Season Stats
# ─────────────────────────────────────────────────────────────────────────────

@cached(ttl=config.CACHE_TTL_GAME_LOGS, key_prefix="season_hitting")
def get_season_hitting_stats(player_id: int, season: int | None = None) -> dict:
    """Return current-season aggregate hitting stats for a batter."""
    season = season or datetime.date.today().year
    raw = statsapi.player_stat_data(player_id, group="hitting", type="season")
    stats = raw.get("stats", [])
    if not stats:
        return {}
    splits = stats[0].get("splits", [])
    return splits[0].get("stat", {}) if splits else {}


@cached(ttl=config.CACHE_TTL_GAME_LOGS, key_prefix="season_pitching")
def get_season_pitching_stats(player_id: int, season: int | None = None) -> dict:
    """Return current-season aggregate pitching stats for a pitcher."""
    season = season or datetime.date.today().year
    raw = statsapi.player_stat_data(player_id, group="pitching", type="season")
    stats = raw.get("stats", [])
    if not stats:
        return {}
    splits = stats[0].get("splits", [])
    return splits[0].get("stat", {}) if splits else {}


# ─────────────────────────────────────────────────────────────────────────────
# L/R Splits
# ─────────────────────────────────────────────────────────────────────────────

@cached(ttl=config.CACHE_TTL_GAME_LOGS, key_prefix="batter_splits")
def get_batter_splits(player_id: int) -> dict[str, dict]:
    """
    Return batter splits vs LHP and RHP.
    Returns: {"vs_L": {stat_dict}, "vs_R": {stat_dict}}
    """
    raw = statsapi.player_stat_data(player_id, group="hitting", type="vsTeamTotal5Y")
    # Fall back to statSplits
    splits_raw = statsapi.player_stat_data(player_id, group="hitting", type="statSplits")
    splits = splits_raw.get("stats", [{}])[0].get("splits", [])
    result: dict[str, dict] = {"vs_L": {}, "vs_R": {}}
    for s in splits:
        split_code = s.get("split", {}).get("code", "")
        if split_code == "vl":
            result["vs_L"] = s.get("stat", {})
        elif split_code == "vr":
            result["vs_R"] = s.get("stat", {})
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Statcast — Batter
# ─────────────────────────────────────────────────────────────────────────────

def _season_date_range(lookback_days: int = 90) -> tuple[str, str]:
    end = datetime.date.today()
    start = end - datetime.timedelta(days=lookback_days)
    # Don't go before March 20 of current year (earliest Opening Day)
    season_start = datetime.date(end.year, 3, 20)
    start = max(start, season_start)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


@cached(ttl=config.CACHE_TTL_STATCAST, key_prefix="statcast_batter")
def get_statcast_batter_stats(player_name: str, lookback_days: int = 60) -> dict:
    """
    Return aggregated Statcast metrics for a batter.

    Returns dict with: barrel_pct, hard_hit_pct, fly_ball_pct,
    avg_launch_angle, avg_exit_velocity, xba, xslg, k_pct, bb_pct, babip
    """
    start, end = _season_date_range(lookback_days)
    try:
        df = pb.statcast_batter_expected_stats(end.split("-")[0])
        # Filter by player name (approximate match)
        name_mask = df["last_name, first_name"].str.lower().str.contains(
            _name_to_statcast(player_name), na=False
        )
        player_df = df[name_mask]
        if player_df.empty:
            log.warning(f"Statcast batter not found for: {player_name}")
            return {}
        row = player_df.iloc[0]
        return {
            "barrel_pct": float(row.get("barrel_batted_rate", 0) or 0),
            "hard_hit_pct": float(row.get("hard_hit_percent", 0) or 0),
            "avg_exit_velocity": float(row.get("avg_hit_speed", 0) or 0),
            "xba": float(row.get("xba", 0) or 0),
            "xslg": float(row.get("xslg", 0) or 0),
            "k_pct": float(row.get("strikeout", 0) or 0),
            "bb_pct": float(row.get("walk", 0) or 0),
        }
    except Exception as exc:
        log.error(f"Statcast batter fetch failed for {player_name}: {exc}")
        return {}


@cached(ttl=config.CACHE_TTL_STATCAST, key_prefix="statcast_batter_detail")
def get_statcast_batter_detail(player_name: str, lookback_days: int = 60) -> dict:
    """
    Fetch raw Statcast pitch-by-pitch and compute fly ball %, barrel %, etc.
    """
    start, end = _season_date_range(lookback_days)
    try:
        # Look up player_id via pybaseball
        lookup = pb.playerid_lookup(*_split_name(player_name))
        if lookup.empty:
            log.warning(f"pybaseball lookup failed for {player_name}")
            return {}
        mlbam_id = int(lookup.iloc[0]["key_mlbam"])
        df = pb.statcast_batter(start, end, player_id=mlbam_id)
        if df.empty:
            return {}

        total = len(df)
        fly_balls = df[df["bb_type"] == "fly_ball"]
        barrels = df[df["launch_speed_angle"] == 6]  # 6 = barrel zone
        hard_hit = df[df["launch_speed"] >= 95]

        return {
            "fly_ball_pct": float(f"{len(fly_balls) / total * 100:.1f}") if total else 0.0,
            "barrel_pct": float(f"{len(barrels) / total * 100:.1f}") if total else 0.0,
            "hard_hit_pct": float(f"{len(hard_hit) / total * 100:.1f}") if total else 0.0,
            "avg_exit_velocity": float(f'{df["launch_speed"].dropna().mean():.1f}') if not df.empty else 0.0,
            "avg_launch_angle": float(f'{df["launch_angle"].dropna().mean():.1f}') if not df.empty else 0.0,
            "pa_count": total,
        }
    except Exception as exc:
        log.error(f"Statcast batter detail failed for {player_name}: {exc}")
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# Statcast — Pitcher
# ─────────────────────────────────────────────────────────────────────────────

@cached(ttl=config.CACHE_TTL_STATCAST, key_prefix="statcast_pitcher")
def get_statcast_pitcher_stats(player_name: str, lookback_days: int = 60) -> dict:
    """
    Return aggregated Statcast + FanGraphs metrics for a pitcher.

    Returns dict with: k_pct, bb_pct, xfip, whiff_rate, k_per_9, hr_per_9
    """
    season = datetime.date.today().year
    try:
        # FanGraphs pitcher leaderboard for xFIP, K%, K/9
        fg = pb.pitching_stats(season, season, qual=1)
        name_mask = fg["Name"].str.lower().str.contains(
            player_name.lower().split()[-1], na=False
        )
        player_fg = fg[name_mask]

        result: dict = {}
        if not player_fg.empty:
            r = player_fg.iloc[0]
            result["k_pct"] = float(r.get("K%", 0) or 0) * 100
            result["bb_pct"] = float(r.get("BB%", 0) or 0) * 100
            result["xfip"] = float(r.get("xFIP", 4.5) or 4.5)
            result["k_per_9"] = float(r.get("K/9", 0) or 0)
            result["whiff_rate"] = float(r.get("SwStr%", 0) or 0) * 100
            result["hr_per_9"] = float(r.get("HR/9", 0) or 0)

        # Supplement with Statcast expected stats
        sc = pb.statcast_pitcher_expected_stats(season)
        sc_mask = sc["last_name, first_name"].str.lower().str.contains(
            _name_to_statcast(player_name), na=False
        )
        player_sc = sc[sc_mask]
        if not player_sc.empty:
            r2 = player_sc.iloc[0]
            result["xba_against"] = float(r2.get("xba", 0) or 0)
            result["xslg_against"] = float(r2.get("xslg", 0) or 0)

        return result
    except Exception as exc:
        log.error(f"Statcast pitcher fetch failed for {player_name}: {exc}")
        return {}


@cached(ttl=config.CACHE_TTL_STATCAST, key_prefix="team_k_rate")
def get_team_strikeout_rate(team_abbrev: str, lookback_days: int = 14) -> float:
    """
    Return a team's K% over the last N days using FanGraphs batting leaderboard.
    Returns 0.0 if not available.
    """
    season = datetime.date.today().year
    try:
        df = pb.batting_stats(season, season, qual=1)
        team_df = df[df["Team"].str.upper() == team_abbrev.upper()]
        if team_df.empty:
            return 0.0
        # Average K% across qualified hitters on the team
        k_pcts = pd.to_numeric(team_df["K%"], errors="coerce").dropna()
        return float(f"{float(k_pcts.mean()) * 100:.1f}") if not k_pcts.empty else 0.0
    except Exception as exc:
        log.error(f"Team K rate fetch failed for {team_abbrev}: {exc}")
        return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Park Factors
# ─────────────────────────────────────────────────────────────────────────────

def get_park_run_factor(venue_name: str) -> float:
    """Return run park factor for a venue (from config). Default 1.0."""
    return config.PARK_RUN_FACTORS.get(venue_name, 1.0)


def get_park_hr_factor(venue_name: str) -> float:
    """Return HR park factor for a venue. Default 1.0."""
    return config.PARK_HR_FACTORS.get(venue_name, 1.0)


# ─────────────────────────────────────────────────────────────────────────────
# Team Runs Per Game
# ─────────────────────────────────────────────────────────────────────────────

@cached(ttl=config.CACHE_TTL_GAME_LOGS, key_prefix="team_runs")
def get_team_runs_per_game(team_id: int, last_n: int = 14) -> float:
    """
    Return average runs scored per game for a team over their last N games.
    """
    try:
        schedule = statsapi.schedule(team=team_id, sportId=1)
        finished_all = [g for g in schedule if g.get("status") == "Final"]
        finished = []
        for i in range(max(0, len(finished_all) - last_n), len(finished_all)):
            finished.append(finished_all[i])
        if not finished:
            return 4.5  # league average fallback
        total_runs = 0
        for g in finished:
            if g.get("home_id") == team_id:
                total_runs += g.get("home_score", 0)
            else:
                total_runs += g.get("away_score", 0)
        return float(f"{total_runs / len(finished):.2f}")
    except Exception as exc:
        log.error(f"Team runs/game fetch failed team_id={team_id}: {exc}")
        return 4.5


# ─────────────────────────────────────────────────────────────────────────────
# Bullpen Fatigue
# ─────────────────────────────────────────────────────────────────────────────

@cached(ttl=config.CACHE_TTL_SCHEDULE, key_prefix="bullpen_fatigue")
def get_bullpen_fatigue(team_id: int, days: int = 3) -> float:
    """
    Estimate bullpen fatigue: total relief innings pitched in last N days.
    Higher = more fatigued. Returns 0.0 if data unavailable.
    """
    try:
        cutoff = datetime.date.today() - datetime.timedelta(days=days)
        schedule = statsapi.schedule(
            team=team_id,
            start_date=cutoff.strftime("%m/%d/%Y"),
            end_date=datetime.date.today().strftime("%m/%d/%Y"),
            sportId=1,
        )
        total_ip = 0.0
        for g in schedule:
            if g.get("status") != "Final":
                continue
            box = statsapi.boxscore_data(g["game_id"])
            team_key = "home" if g.get("home_id") == team_id else "away"
            pitchers = box.get(team_key, {}).get("pitchers", [])
            # Skip starter (index 0), sum bullpen IP
            for pid in pitchers[1:]:
                p_stats = box.get("playerInfo", {}).get(str(pid), {})
                ip_str = p_stats.get("stats", {}).get("pitching", {}).get("inningsPitched", "0")
                total_ip = total_ip + float(ip_str or 0)
        return float(f"{total_ip:.1f}")
    except Exception as exc:
        log.error(f"Bullpen fatigue fetch failed: {exc}")
        return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Internal Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _name_to_statcast(full_name: str) -> str:
    """Convert 'First Last' to 'last, first' for Statcast search."""
    parts = full_name.strip().split()
    if len(parts) >= 2:
        return f"{parts[-1].lower()}"
    return full_name.lower()


def _split_name(full_name: str) -> tuple[str, str]:
    """Split 'First Last' into (last, first) for pybaseball lookup."""
    parts = full_name.strip().split()
    if len(parts) >= 2:
        return parts[-1], parts[0]
    return full_name, ""
