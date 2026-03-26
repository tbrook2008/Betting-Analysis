"""
picks/pick_generator.py — Orchestrates the full daily pick pipeline.

Flow:
  1. Fetch today's schedule
  2. Fetch PrizePicks + DraftKings lines
  3. For each player prop line, determine which model to use
  4. Run signals → confidence_scorer → PickResult
  5. Filter by min_confidence, sort by confidence descending
  6. Return List[PickResult]
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field, asdict
from typing import Optional

import pandas as pd

import config
from data import mlb_client as mlb
from data.prizepicks_scraper import get_prizepicks_lines
from data.draftkings_scraper import get_draftkings_lines
from analysis import confidence_scorer as scorer
from analysis.hits_model import generate_hits_signals, generate_total_bases_signals
from analysis.hr_model import generate_hr_signals
from analysis.pitcher_model import generate_pitcher_k_signals
from analysis.totals_model import generate_totals_signals, project_total_runs
from utils.logger import get_logger

log = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Data Model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PickResult:
    player_name: str
    team: str
    opponent: str
    prop_type: str
    line: float
    recommendation: str          # "OVER" | "UNDER" | "NO PLAY"
    confidence: int              # 0–100
    reasoning: list[str]
    source: str                  # "PrizePicks" | "DraftKings"
    game_time: str
    prop_type_key: str           # internal key: "hits", "home_runs", etc.
    signal_contributions: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


# Prop-type → internal key mapping
_PROP_TYPE_MAP: dict[str, str] = {
    # PrizePicks label → internal key
    "hits": "hits",
    "total bases": "total_bases",
    "hits+runs+rbis": "hits",
    "home runs": "home_runs",
    "pitcher strikeouts": "pitcher_ks",
    "strikeouts": "pitcher_ks",
    "runs": "hits",
    "rbis": "hits",
    # DraftKings labels
    "batter_hits": "hits",
    "batter_home_runs": "home_runs",
    "batter_total_bases": "total_bases",
    "pitcher_strikeouts": "pitcher_ks",
}


# ─────────────────────────────────────────────────────────────────────────────
# Main Entry Point
# ─────────────────────────────────────────────────────────────────────────────

def generate_daily_picks(
    date: datetime.date | None = None,
    min_confidence: int = config.MIN_CONFIDENCE,
    sources: list[str] | None = None,
) -> list[PickResult]:
    """
    Generate today's best picks across all player prop types.

    Args:
        date:            Date to run (default: today)
        min_confidence:  Minimum confidence score to include (default from config)
        sources:         ["PrizePicks", "DraftKings"] or a subset

    Returns:
        List of PickResult objects sorted by confidence descending.
    """
    date = date or datetime.date.today()
    sources = sources or ["PrizePicks", "DraftKings"]
    log.info(f"Generating picks for {date} from {sources}")

    # ── 1. Fetch schedule to build game context ──────────────────────────────
    schedule = mlb.get_schedule(date)
    game_ctx = _build_game_context(schedule)

    # ── 2. Collect lines from all sources ────────────────────────────────────
    all_lines: list[dict] = []

    if "PrizePicks" in sources:
        pp_df = get_prizepicks_lines()
        if not pp_df.empty:
            pp_df["source"] = "PrizePicks"
            all_lines.extend(pp_df.to_dict("records"))

    if "DraftKings" in sources:
        dk_df = get_draftkings_lines()
        if not dk_df.empty:
            dk_df["source"] = "DraftKings"
            # Align columns to PrizePicks schema
            if "home_team" in dk_df.columns and "team" not in dk_df.columns:
                dk_df["team"] = ""
            if "opponent" not in dk_df.columns:
                dk_df["opponent"] = ""
            if "position" not in dk_df.columns:
                dk_df["position"] = ""
            all_lines.extend(dk_df.to_dict("records"))

    if not all_lines:
        log.warning("No lines found from any source.")
        return []

    log.info(f"Processing {len(all_lines)} total prop lines")

    # ── 3. Score each line ───────────────────────────────────────────────────
    picks: list[PickResult] = []

    for line_row in all_lines:
        try:
            pick = _score_line(line_row, game_ctx)
            if pick and pick.recommendation != "NO PLAY" and pick.confidence >= min_confidence:
                picks.append(pick)
        except Exception as exc:
            log.debug(f"Skipped line for {line_row.get('player_name', '?')}: {exc}")

    # ── 4. Sort by confidence descending ─────────────────────────────────────
    picks.sort(key=lambda p: p.confidence, reverse=True)
    log.info(f"Generated {len(picks)} picks (min confidence={min_confidence})")
    return picks


def generate_player_picks(
    player_name: str,
    min_confidence: int = 0,
) -> list[PickResult]:
    """Return all picks for a specific player."""
    all_picks = generate_daily_picks(min_confidence=min_confidence)
    return [p for p in all_picks if player_name.lower() in p.player_name.lower()]


# ─────────────────────────────────────────────────────────────────────────────
# Game Context Builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_game_context(schedule: list[dict]) -> dict[str, dict]:
    """
    Build a lookup dict: team_name → game context.
    Context includes: opponent, venue, home_pitcher_name, away_pitcher_name,
                      home_pitcher_throws, away_pitcher_throws
    """
    ctx: dict[str, dict] = {}
    for g in schedule:
        home = g.get("home_team", "")
        away = g.get("away_team", "")
        venue = g.get("venue", "")
        game_time = g.get("game_datetime", "")

        base = {
            "venue": venue,
            "game_time": game_time,
            "home_pitcher_name": g.get("home_pitcher_name", "TBD"),
            "away_pitcher_name": g.get("away_pitcher_name", "TBD"),
            "home_pitcher_id": g.get("home_pitcher_id"),
            "away_pitcher_id": g.get("away_pitcher_id"),
            "home_team_id": g.get("home_id"),
            "away_team_id": g.get("away_id"),
        }
        ctx[home.lower()] = {**base, "is_home": True, "opponent": away, "team": home}
        ctx[away.lower()] = {**base, "is_home": False, "opponent": home, "team": away}

    return ctx


# ─────────────────────────────────────────────────────────────────────────────
# Per-Line Scoring
# ─────────────────────────────────────────────────────────────────────────────

def _score_line(row: dict, game_ctx: dict[str, dict]) -> PickResult | None:
    """Score a single prop line row and return a PickResult."""
    player_name = str(row.get("player_name", "")).strip()
    prop_label = str(row.get("prop_type", "")).strip()
    line = float(row.get("line_score", 0) or 0)
    source = str(row.get("source", "PrizePicks"))
    team = str(row.get("team", "")).strip()
    opponent = str(row.get("opponent", "")).strip()
    game_time = str(row.get("game_time", ""))

    if not player_name or line == 0:
        return None

    # Map prop label → internal key
    prop_key = _PROP_TYPE_MAP.get(prop_label.lower())
    if prop_key is None:
        return None  # Unknown/unsupported prop type

    # Look up game context
    gctx = game_ctx.get(team.lower(), {})
    venue = gctx.get("venue", "")
    is_home = gctx.get("is_home", True)

    # Determine opposing pitcher info
    if is_home:
        opp_pitcher_name = gctx.get("away_pitcher_name", "TBD")
        opp_pitcher_id = gctx.get("away_pitcher_id")
        pitcher_throws = "R"  # default; could enhance with roster lookup
    else:
        opp_pitcher_name = gctx.get("home_pitcher_name", "TBD")
        opp_pitcher_id = gctx.get("home_pitcher_id")
        pitcher_throws = "R"

    # ── Generate signals based on prop type ──────────────────────────────────
    signals: dict[str, float] = {}
    projected_value: float | None = None

    if prop_key == "hits":
        signals = generate_hits_signals(
            player_name=player_name,
            opp_pitcher_name=opp_pitcher_name,
            venue=venue,
            pitcher_throws=pitcher_throws,
            opp_pitcher_id=opp_pitcher_id,
        )
    elif prop_key == "total_bases":
        signals = generate_total_bases_signals(
            player_name=player_name,
            opp_pitcher_name=opp_pitcher_name,
            venue=venue,
            pitcher_throws=pitcher_throws,
            opp_pitcher_id=opp_pitcher_id,
        )
    elif prop_key == "home_runs":
        signals = generate_hr_signals(
            player_name=player_name,
            opp_pitcher_name=opp_pitcher_name,
            venue=venue,
            opp_pitcher_id=opp_pitcher_id,
        )
    elif prop_key == "pitcher_ks":
        opp_team = opponent
        signals = generate_pitcher_k_signals(
            pitcher_name=player_name,
            opp_team_abbrev=_team_to_abbrev(opp_team),
            is_home=is_home,
        )

    if not signals:
        return None

    # ── Score ────────────────────────────────────────────────────────────────
    result = scorer.score(
        signals=signals,
        prop_type=prop_key,
        line=line,
        projected_value=projected_value,
    )

    return PickResult(
        player_name=player_name,
        team=team,
        opponent=opponent,
        prop_type=prop_label,
        line=line,
        recommendation=result.recommendation,
        confidence=result.confidence,
        reasoning=result.reasoning,
        source=source,
        game_time=game_time,
        prop_type_key=prop_key,
        signal_contributions=result.signal_contributions,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_TEAM_ABBREV_MAP: dict[str, str] = {
    "new york yankees": "NYY", "new york mets": "NYM",
    "los angeles dodgers": "LAD", "los angeles angels": "LAA",
    "boston red sox": "BOS", "chicago cubs": "CHC",
    "chicago white sox": "CWS", "houston astros": "HOU",
    "atlanta braves": "ATL", "philadelphia phillies": "PHI",
    "san francisco giants": "SF", "san diego padres": "SD",
    "seattle mariners": "SEA", "minnesota twins": "MIN",
    "st. louis cardinals": "STL", "cleveland guardians": "CLE",
    "toronto blue jays": "TOR", "tampa bay rays": "TB",
    "baltimore orioles": "BAL", "miami marlins": "MIA",
    "pittsburgh pirates": "PIT", "cincinnati reds": "CIN",
    "colorado rockies": "COL", "arizona diamondbacks": "ARI",
    "washington nationals": "WSH", "milwaukee brewers": "MIL",
    "kansas city royals": "KC", "detroit tigers": "DET",
    "texas rangers": "TEX", "oakland athletics": "OAK",
}


def _team_to_abbrev(team_name: str) -> str:
    return _TEAM_ABBREV_MAP.get(team_name.lower(), team_name[:3].upper())
