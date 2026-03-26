"""
picks/parlay_builder.py — Correlation-aware parlay builder.

Builds Power Play (2-leg) and Flex Play (3–5 leg) parlays from top picks,
penalizing same-game and same-team combinations to reduce correlation.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field, asdict
from typing import Literal

import config
from picks.pick_generator import PickResult
from utils.logger import get_logger

log = get_logger(__name__)

ParlayType = Literal["Power Play", "Flex Play"]


@dataclass
class ParlayLeg:
    player_name: str
    prop_type: str
    line: float
    recommendation: str
    confidence: int
    team: str
    game_time: str


@dataclass
class Parlay:
    parlay_type: ParlayType
    legs: list[ParlayLeg]
    num_legs: int
    avg_confidence: float
    correlation_score: float   # lower = better (less correlated)
    combined_score: float      # avg_confidence - correlation_penalty

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


def build_parlays(
    picks: list[PickResult],
    top_n_power: int = 3,
    top_n_flex: int = 3,
    max_legs: int = config.PARLAY_MAX_LEGS,
) -> dict[str, list[Parlay]]:
    """
    Generate the best Power Play and Flex Play parlays from a pick list.

    Args:
        picks:          Sorted list of PickResult (confidence descending)
        top_n_power:    Number of 2-leg Power Plays to return
        top_n_flex:     Number of 3–5 leg Flex Plays to return
        max_legs:       Maximum legs in a Flex Play (3–5)

    Returns:
        Dict: {"power_plays": [...], "flex_plays": [...]}
    """
    # Only use picks with recommendation != NO PLAY
    valid = [p for p in picks if p.recommendation != "NO PLAY"]

    if len(valid) < 2:
        log.warning("Not enough valid picks to build parlays.")
        return {"power_plays": [], "flex_plays": []}

    power_plays = _build_power_plays(valid, top_n_power)
    flex_plays = _build_flex_plays(valid, top_n_flex, max_legs)

    log.info(
        f"Built {len(power_plays)} Power Plays, {len(flex_plays)} Flex Plays"
    )
    return {"power_plays": power_plays, "flex_plays": flex_plays}


# ─────────────────────────────────────────────────────────────────────────────
# Power Play (2-leg)
# ─────────────────────────────────────────────────────────────────────────────

def _build_power_plays(picks: list[PickResult], top_n: int) -> list[Parlay]:
    """Generate top-N 2-leg Power Plays sorted by combined score."""
    candidates: list[Parlay] = []

    for p1, p2 in itertools.combinations(picks, 2):
        corr = _correlation(p1, p2)
        avg_conf = (p1.confidence + p2.confidence) / 2
        combined = avg_conf - corr * 10   # corr is in [0, 1], penalty up to 10 pts

        parlay = Parlay(
            parlay_type="Power Play",
            legs=[_to_leg(p1), _to_leg(p2)],
            num_legs=2,
            avg_confidence=round(avg_conf, 1),
            correlation_score=round(corr, 3),
            combined_score=round(combined, 1),
        )
        candidates.append(parlay)

    candidates.sort(key=lambda x: x.combined_score, reverse=True)
    return candidates[:top_n]


# ─────────────────────────────────────────────────────────────────────────────
# Flex Play (3–5 legs)
# ─────────────────────────────────────────────────────────────────────────────

def _build_flex_plays(
    picks: list[PickResult], top_n: int, max_legs: int
) -> list[Parlay]:
    """Generate top-N Flex Plays (3–max_legs) sorted by combined score."""
    candidates: list[Parlay] = []
    pool = picks[:20]  # Only consider top 20 picks for performance

    for n_legs in range(config.PARLAY_MIN_LEGS + 1, max_legs + 1):
        for combo in itertools.combinations(pool, n_legs):
            total_corr = sum(
                _correlation(a, b)
                for a, b in itertools.combinations(combo, 2)
            )
            avg_corr = total_corr / max(len(list(itertools.combinations(combo, 2))), 1)
            avg_conf = sum(p.confidence for p in combo) / n_legs
            combined = avg_conf - avg_corr * 10

            parlay = Parlay(
                parlay_type="Flex Play",
                legs=[_to_leg(p) for p in combo],
                num_legs=n_legs,
                avg_confidence=round(avg_conf, 1),
                correlation_score=round(avg_corr, 3),
                combined_score=round(combined, 1),
            )
            candidates.append(parlay)

    candidates.sort(key=lambda x: x.combined_score, reverse=True)

    # Deduplicate: avoid returning parlays with same players under different sizes
    seen: set[frozenset] = set()
    deduped: list[Parlay] = []
    for p in candidates:
        key = frozenset(leg.player_name + leg.prop_type for leg in p.legs)
        if key not in seen:
            seen.add(key)
            deduped.append(p)
        if len(deduped) >= top_n:
            break

    return deduped


# ─────────────────────────────────────────────────────────────────────────────
# Correlation
# ─────────────────────────────────────────────────────────────────────────────

def _correlation(a: PickResult, b: PickResult) -> float:
    """
    Estimate correlation between two picks.
    Higher = more correlated (bad for parlays).
    Returns a value in [0, 1].
    """
    corr = 0.0

    # Same game
    same_game = (
        a.team and b.team and (
            a.team == b.team or a.opponent == b.team or
            a.team == b.opponent
        )
    )
    if same_game:
        corr += config.PARLAY_SAME_GAME_PENALTY

    # Same team (same game already adds penalty; this is for e.g. two batters same team)
    if a.team and b.team and a.team == b.team:
        corr += config.PARLAY_SAME_TEAM_PENALTY

    # Same prop type on different teams is generally low correlation
    return min(corr, 1.0)


def _to_leg(pick: PickResult) -> ParlayLeg:
    return ParlayLeg(
        player_name=pick.player_name,
        prop_type=pick.prop_type,
        line=pick.line,
        recommendation=pick.recommendation,
        confidence=pick.confidence,
        team=pick.team,
        game_time=pick.game_time,
    )
