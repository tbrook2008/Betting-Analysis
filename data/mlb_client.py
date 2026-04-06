"""
data/mlb_client.py — MLB Stats API + pybaseball (Statcast/FanGraphs) wrappers.

All functions are cached via utils.cache.cached() to avoid hammering APIs.
All data is returned as pandas DataFrames or plain Python dicts.
"""
from __future__ import annotations

import datetime
from typing import Optional
from functools import lru_cache

import pandas as pd
import numpy as np
import statsapi
import pybaseball as pb

import config
from utils.cache import cached
from utils.logger import get_logger

log = get_logger(__name__)

# Silence pybaseball's progress bar
pb.cache.enable()

# ── League-wide Data Caching (to avoid re-parsing massive CSVs in loops) ───
@lru_cache(maxsize=1) # Cache 1 year at a time for each position
def _get_league_expected_stats(year: int, pos: str = "batter") -> pd.DataFrame:
    log.debug(f"Fetching league-wide expected stats for {pos} in {year}")
    if pos == "pitcher":
        return pb.statcast_pitcher_expected_stats(year)
    return pb.statcast_batter_expected_stats(year)

@lru_cache(maxsize=1)
def _get_league_exit_velo(year: int, pos: str = "batter") -> pd.DataFrame:
    log.debug(f"Fetching league-wide exit velo/barrels for {pos} in {year}")
    if pos == "pitcher":
        return pb.statcast_pitcher_exitvelo_barrels(year)
    return pb.statcast_batter_exitvelo_barrels(year)

@lru_cache(maxsize=1)
def _get_league_batting_stats(year: int) -> pd.DataFrame:
    log.debug(f"Fetching league-wide batting stats for {year}")
    return pb.batting_stats(year, year, qual=1)

@lru_cache(maxsize=1)
def _get_league_pitching_stats(year: int) -> pd.DataFrame:
    log.debug(f"Fetching league-wide pitching stats for {year}")
    return pb.pitching_stats(year, year, qual=1)


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
    """
    Look up MLB player ID by full name. 
    Improved to prefer ACTIVE players and handle common name ambiguity.
    """
    results = statsapi.lookup_player(name)
    if not results:
        log.warning(f"Player not found: {name}")
        return None
    
    # If multiple results, primary check: find the active one
    active = [p for p in results if p.get("active", False)]
    if active:
        if len(active) > 1:
            log.info(f"Multiple active players found for '{name}', using first matching ID: {active[0]['id']}")
        return active[0]["id"]
    
    # Fallback to the first result regardless of activity status
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
    
    rows = []
    # For gameLog, the 'stats' list itself contains the individual games
    for entry in stats[-last_n:]:
        stat = entry.get("stats", {})
        rows.append({
            "date": entry.get("date"),
            "H": int(stat.get("hits", 0)),
            "2B": int(stat.get("doubles", 0)),
            "3B": int(stat.get("triples", 0)),
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
    stats = splits_raw.get("stats", [])
    splits = stats[0].get("splits", []) if stats else []
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

def _season_date_range(lookback_days: int = 60) -> tuple[str, str]:
    """
    Return a date range for Statcast lookups. 
    If today is before April 1st, look back into the previous season.
    """
    end = datetime.date.today()
    start = end - datetime.timedelta(days=lookback_days)
    
    # If early in the season (before April 15), ensure we include end of last season
    if end.month < 4 or (end.month == 4 and end.day < 15):
        # Look back from Oct 1st of previous year
        prev_year = end.year - 1
        start = datetime.date(prev_year, 8, 1)
        # If we are in the off-season, 'end' should be the end of the previous season
        if end.month < 3:
             end = datetime.date(prev_year, 11, 1)
             
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


@cached(ttl=config.CACHE_TTL_STATCAST, key_prefix="statcast_batter")
def get_statcast_batter_stats(player_name: str) -> dict:
    """
    Return aggregated Statcast metrics for a batter using memoized league-wide data.
    """
    current_year = datetime.date.today().year
    sc_name = _name_to_statcast(player_name)
    
    for year in [current_year, current_year - 1]:
        try:
            # 1. Expected Stats (xBA, xSLG, PA)
            x_df = _get_league_expected_stats(year, "batter")
            if x_df.empty:
                continue
            
            x_mask = x_df["last_name, first_name"].str.lower().str.contains(sc_name, na=False)
            x_player = x_df[x_mask]
            if x_player.empty:
                continue
                
            x_row = x_player.iloc[0]
            pa = int(x_row.get("pa", 0) or 0)
            
            # Sample size check
            if year == current_year and pa < 50:
                log.debug(f"Low sample size for {player_name} in {year} ({pa} PA), falling back.")
                continue

            # 2. Exit Velo & Barrels
            ev_df = _get_league_exit_velo(year, "batter")
            ev_mask = ev_df["last_name, first_name"].str.lower().str.contains(sc_name, na=False)
            ev_player = ev_df[ev_mask]
            
            result = {
                "xba": float(x_row.get("est_ba", 0) or 0),
                "xslg": float(x_row.get("est_slg", 0) or 0),
                "xwoba": float(x_row.get("est_woba", 0) or 0),
                "pa": pa,
                "data_year": year
            }
            
            if not ev_player.empty:
                ev_row = ev_player.iloc[0]
                result.update({
                    "barrel_pct": float(ev_row.get("brl_percent", 0) or 0),
                    "hard_hit_pct": float(ev_row.get("ev95percent", 0) or 0),
                    "avg_exit_velocity": float(ev_row.get("avg_hit_speed", 0) or 0),
                })
                
            return result
        except Exception as exc:
            log.debug(f"Statcast batter fetch failed for {player_name} in {year}: {exc}")
            continue
            
    log.warning(f"Statcast batter not found for: {player_name}")
    return {}


@cached(ttl=config.CACHE_TTL_STATCAST, key_prefix="statcast_batter_detail")
def get_statcast_batter_detail(player_name: str, lookback_days: int = 30) -> dict:
    """
    Fetch raw Statcast pitch-by-pitch and compute fly ball %, etc.
    CRITICAL: This is slow. Used only as a fallback for specific metrics (Fly Ball%).
    """
    end = datetime.date.today()
    start = end - datetime.timedelta(days=lookback_days)
    
    if end.month < 3:
        start = datetime.date(end.year - 1, 9, 1)
        end = datetime.date(end.year - 1, 10, 5)

    try:
        lookup = pb.playerid_lookup(*_split_name(player_name))
        if lookup.empty:
            return {}
        mlbam_id = int(lookup.iloc[0]["key_mlbam"])
        df = pb.statcast_batter(start, end, player_id=mlbam_id)
        if df.empty:
            return {}

        df_bbe = df.dropna(subset=['launch_speed', 'launch_angle'])
        total_bbe = len(df_bbe)
        if not total_bbe:
            return {}

        fly_balls = df_bbe[df_bbe["bb_type"] == "fly_ball"]
        barrels = df_bbe[df_bbe["launch_speed_angle"] == 6]
        hard_hit = df_bbe[df_bbe["launch_speed"] >= 95]

        return {
            "fly_ball_pct": float(f"{len(fly_balls) / total_bbe * 100:.1f}"),
            "barrel_pct": float(f"{len(barrels) / total_bbe * 100:.1f}"),
            "hard_hit_pct": float(f"{len(hard_hit) / total_bbe * 100:.1f}"),
            "avg_exit_velocity": float(f'{df_bbe["launch_speed"].mean():.1f}'),
            "bbe_count": total_bbe,
        }
    except Exception as exc:
        log.debug(f"Statcast detail failed for {player_name}: {exc}")
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# Statcast — Pitcher
# ─────────────────────────────────────────────────────────────────────────────

@cached(ttl=config.CACHE_TTL_STATCAST, key_prefix="statcast_pitcher")
def get_statcast_pitcher_stats(player_name: str) -> dict:
    """
    Return aggregated Statcast + FanGraphs metrics for a pitcher using league caching.
    """
    current_year = datetime.date.today().year
    sc_name = _name_to_statcast(player_name)
    
    for year in [current_year, current_year - 1]:
        try:
            result = {}
            # 1. FanGraphs Pitching Leaderboard (K%, xFIP)
            fg = _get_league_pitching_stats(year)
            if not fg.empty:
                # Use split name for more flexible match
                last_name = player_name.lower().split()[-1]
                fg_mask = fg["Name"].str.lower().str.contains(last_name, na=False)
                player_fg = fg[fg_mask]
                if not player_fg.empty:
                    r = player_fg.iloc[0]
                    ip = float(r.get("IP", 0) or 0)
                    if year == current_year and ip < 15:
                        log.debug(f"Low sample size for {player_name} in {year} ({ip} IP), falling back.")
                        continue

                    result.update({
                        "k_pct": float(r.get("K%", 0) or 0) * 100,
                        "bb_pct": float(r.get("BB%", 0) or 0) * 100,
                        "xfip": float(r.get("xFIP", 4.5) or 4.5),
                        "k_per_9": float(r.get("K/9", 0) or 0),
                        "whiff_rate": float(r.get("SwStr%", 0) or 0) * 100,
                        "hr_per_9": float(r.get("HR/9", 0) or 0),
                        "data_year_fg": year
                    })

            # 2. Statcast Expected Stats (xBA against)
            sc = _get_league_expected_stats(year, "pitcher")
            if not sc.empty:
                sc_mask = sc["last_name, first_name"].str.lower().str.contains(sc_name, na=False)
                player_sc = sc[sc_mask]
                if not player_sc.empty:
                    r2 = player_sc.iloc[0]
                    result.update({
                        "xba_against": float(r2.get("est_ba", 0) or 0),
                        "xslg_against": float(r2.get("est_slg", 0) or 0),
                        "data_year_sc": year
                    })
            
            # 3. Statcast Exit Velo against (Barrel%)
            ev = _get_league_exit_velo(year, "pitcher")
            if not ev.empty:
                ev_mask = ev["last_name, first_name"].str.lower().str.contains(sc_name, na=False)
                player_ev = ev[ev_mask]
                if not player_ev.empty:
                    r3 = player_ev.iloc[0]
                    result.update({
                        "barrel_pct_against": float(r3.get("brl_percent", 0) or 0),
                        "hard_hit_pct_against": float(r3.get("ev95percent", 0) or 0),
                    })

            if result:
                return result
        except Exception as exc:
            log.debug(f"Statcast pitcher fetch failed for {player_name} in {year}: {exc}")
            continue

    return result


@cached(ttl=config.CACHE_TTL_STATCAST, key_prefix="team_k_rate")
def get_team_strikeout_rate(team_abbrev: str, lookback_days: int = 14) -> float:
    """
    Return a team's K% over the current season using memoized league-wide data.
    """
    season = datetime.date.today().year
    try:
        # Use our memoized league data instead of downloading fresh every time
        df = _get_league_batting_stats(season)
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
# Daily Boxscores (For Immediate Grading)
# ─────────────────────────────────────────────────────────────────────────────

@cached(ttl=3600, key_prefix="daily_boxscores_v3")
def get_daily_boxscores(date_str: str) -> dict:
    """
    Fetch and aggregate all player stats from a specific day's boxscores.
    Returns: { player_id: {"batting": {...}, "pitching": {...}} }
    """
    try:
        # Date string must be MM/DD/YYYY for statsapi.schedule
        d_obj = datetime.datetime.fromisoformat(date_str)
        fmt_date = d_obj.strftime("%m/%d/%Y")
    except ValueError:
        fmt_date = date_str
        
    games = statsapi.schedule(date=fmt_date)
    aggregated = {}
    
    for g in games:
        try:
            box = statsapi.boxscore_data(g['game_id'])
            
            # Parse Batters
            for side in ['awayBatters', 'homeBatters']:
                for b in box.get(side, []):
                    pid = b.get('personId')
                    if pid:
                        pid_int = int(pid)
                        if pid_int not in aggregated: aggregated[pid_int] = {"batting": {}, "pitching": {}}
                        aggregated[pid_int]["batting"]["hits"] = aggregated[pid_int]["batting"].get("hits", 0) + int(b.get("h", 0))
                        # Note: the statsapi object has 'doubles', 'triples', and 'hr' instead of 'homeRuns' inside these flat lists
                        aggregated[pid_int]["batting"]["doubles"] = aggregated[pid_int]["batting"].get("doubles", 0) + int(b.get("doubles", 0))
                        aggregated[pid_int]["batting"]["triples"] = aggregated[pid_int]["batting"].get("triples", 0) + int(b.get("triples", 0))
                        aggregated[pid_int]["batting"]["homeRuns"] = aggregated[pid_int]["batting"].get("homeRuns", 0) + int(b.get("hr", 0))
                        
            # Parse Pitchers
            for side in ['awayPitchers', 'homePitchers']:
                for p in box.get(side, []):
                    pid = p.get('personId')
                    if pid:
                        pid_int = int(pid)
                        if pid_int not in aggregated: aggregated[pid_int] = {"batting": {}, "pitching": {}}
                        aggregated[pid_int]["pitching"]["strikeOuts"] = aggregated[pid_int]["pitching"].get("strikeOuts", 0) + int(p.get("k", 0))
                        
        except Exception as exc:
            log.warning(f"Failed to fetch boxscore for game {g.get('game_id')}: {exc}")
            
    return aggregated

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
