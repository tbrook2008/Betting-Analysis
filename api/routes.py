"""
api/routes.py — All FastAPI endpoints for the MLB Betting Analysis system.

Endpoints:
  GET /health                      Health check
  GET /picks                       Full daily picks list
  GET /picks/player/{name}         Picks for a specific player
  GET /parlays                     Top Power Play and Flex Play parlays
  GET /lines/prizepicks            Raw PrizePicks lines
  GET /lines/draftkings            Raw DraftKings lines
  GET /lines/compare/{player}      Line comparison across both books
  GET /cache/info                  Cache stats
  POST /cache/clear                Clear all caches
"""
from __future__ import annotations

import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

import config
from picks.pick_generator import generate_daily_picks, generate_player_picks
from picks.parlay_builder import build_parlays
from data.prizepicks_scraper import get_prizepicks_lines, list_prizepicks_prop_types
from data.draftkings_scraper import get_draftkings_lines, compare_lines
from utils.cache import cache_info, clear_cache
from utils.logger import get_logger

log = get_logger(__name__)
router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/health", tags=["Meta"])
def health():
    return {
        "status": "ok",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "version": "1.0.0",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Picks
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/picks", tags=["Picks"])
def get_picks(
    date: Optional[str] = Query(None, description="Date YYYY-MM-DD (default: today)"),
    min_confidence: int = Query(config.MIN_CONFIDENCE, ge=0, le=100),
    source: Optional[str] = Query(None, description="PrizePicks | DraftKings | all"),
):
    """
    Return today's (or given date's) picks, sorted by confidence descending.
    """
    parsed_date = None
    if date:
        try:
            parsed_date = datetime.date.fromisoformat(date)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid date format: {date}")

    sources: list[str] | None = None
    if source and source.lower() != "all":
        cap = source.strip().title().replace("Prizepicks", "PrizePicks").replace("Draftkings", "DraftKings")
        sources = [cap]

    picks = generate_daily_picks(
        date=parsed_date,
        min_confidence=min_confidence,
        sources=sources,
    )

    return {
        "date": (parsed_date or datetime.date.today()).isoformat(),
        "count": len(picks),
        "min_confidence": min_confidence,
        "picks": [p.to_dict() for p in picks],
    }


@router.get("/picks/player/{player_name}", tags=["Picks"])
def get_player_picks(
    player_name: str,
    min_confidence: int = Query(0, ge=0, le=100),
):
    """Return all picks for a specific player (partial name match)."""
    picks = generate_player_picks(player_name, min_confidence=min_confidence)
    if not picks:
        return {"player": player_name, "count": 0, "picks": []}
    return {
        "player": player_name,
        "count": len(picks),
        "picks": [p.to_dict() for p in picks],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Parlays
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/parlays", tags=["Parlays"])
def get_parlays(
    min_confidence: int = Query(config.HIGH_CONFIDENCE, ge=0, le=100),
    top_n: int = Query(3, ge=1, le=10),
    max_legs: int = Query(config.PARLAY_MAX_LEGS, ge=2, le=5),
):
    """
    Return top Power Play and Flex Play parlays from today's best picks.
    """
    picks = generate_daily_picks(min_confidence=min_confidence)
    parlays = build_parlays(picks, top_n_power=top_n, top_n_flex=top_n, max_legs=max_legs)

    return {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "picks_pool_size": len(picks),
        "power_plays": [p.to_dict() for p in parlays["power_plays"]],
        "flex_plays": [p.to_dict() for p in parlays["flex_plays"]],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Lines
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/lines/prizepicks", tags=["Lines"])
def get_pp_lines(
    prop_type: Optional[str] = Query(None, description="Filter by prop type"),
):
    """Return raw PrizePicks lines (optionally filtered by prop type)."""
    df = get_prizepicks_lines()
    if df.empty:
        return {"count": 0, "lines": [], "available_prop_types": []}

    if prop_type:
        df = df[df["prop_type"].str.lower() == prop_type.lower()]

    return {
        "count": len(df),
        "available_prop_types": list_prizepicks_prop_types(),
        "lines": df.to_dict("records"),
    }


@router.get("/lines/draftkings", tags=["Lines"])
def get_dk_lines(
    prop_type: Optional[str] = Query(None, description="Filter by prop type"),
):
    """Return raw DraftKings lines (optionally filtered by prop type)."""
    df = get_draftkings_lines()
    if df.empty:
        return {
            "count": 0,
            "lines": [],
            "note": "Set ODDS_API_KEY in .env to enable DraftKings lines.",
        }

    if prop_type:
        df = df[df["prop_type"].str.lower() == prop_type.lower()]

    return {"count": len(df), "lines": df.to_dict("records")}


@router.get("/lines/compare/{player_name}", tags=["Lines"])
def get_line_comparison(
    player_name: str,
    prop_type: str = Query(..., description="e.g. 'Hits', 'Home Runs', 'Pitcher Strikeouts'"),
):
    """Compare PrizePicks and DraftKings lines for a player/prop combo."""
    result = compare_lines(player_name, prop_type)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Cache Management
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/cache/info", tags=["Admin"])
def get_cache_info():
    """Return current cache statistics."""
    return cache_info()


@router.post("/cache/clear", tags=["Admin"])
def clear_all_caches():
    """Clear all cached data (forces fresh API fetches)."""
    clear_cache()
    return {"status": "cleared"}
