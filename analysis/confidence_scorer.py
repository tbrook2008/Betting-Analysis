"""
analysis/confidence_scorer.py — Weighted signal → 0–100 confidence score.

Each prop type has its own signal weight map (in config.py).
Signals are normalized to [-1, +1], weighted, summed, then mapped to [0, 100].
A score > 50 means OVER; < 50 means UNDER. Distance from 50 = confidence level.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np

import config
from utils.logger import get_logger

log = get_logger(__name__)

PropType = Literal["hits", "total_bases", "home_runs", "pitcher_ks", "game_total"]
Recommendation = Literal["OVER", "UNDER", "NO PLAY"]


@dataclass
class ScoreResult:
    prop_type: str
    raw_score: float           # 0–100
    confidence: int            # 0–100 integer
    recommendation: Recommendation
    reasoning: list[str]       # human-readable bullet points
    signal_contributions: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "prop_type": self.prop_type,
            "confidence": self.confidence,
            "recommendation": self.recommendation,
            "reasoning": self.reasoning,
            "signal_contributions": self.signal_contributions,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Normalization ranges for each signal
# ─────────────────────────────────────────────────────────────────────────────

_SIGNAL_RANGES: dict[str, tuple[float, float, bool]] = {
    # (lo, hi, invert)
    # invert=True means higher raw value = negative signal
    "rolling_avg_7":       (0.150, 0.350, False),
    "rolling_avg_14":      (0.150, 0.350, False),
    "rolling_avg_30":      (0.150, 0.350, False),
    "handedness_split":    (0.150, 0.350, False),
    "park_hit_factor":     (0.90,  1.20,  False),
    "park_run_factor":     (0.90,  1.20,  False),
    "park_hr_factor":      (0.85,  1.25,  False),
    "opp_pitcher_k_pct":   (10.0,  35.0,  True),    # high K% = fewer hits
    "barrel_pct":          (0.0,   20.0,  False),
    "hard_hit_pct":        (20.0,  60.0,  False),
    "fly_ball_pct":        (15.0,  55.0,  False),
    "opp_hr_per_9":        (0.5,   2.5,   False),
    "wind_boost":          (-0.15, 0.15,  False),
    "hr_rate_30d":         (0.0,   10.0,  False),
    "k_per_9":             (4.0,   14.0,  False),
    "k_pct":               (10.0,  40.0,  False),
    "whiff_rate":          (15.0,  45.0,  False),
    "xfip":                (2.5,   6.5,   True),     # lower xFIP = better pitcher
    "starter1_xfip":       (2.5,   6.5,   True),
    "starter2_xfip":       (2.5,   6.5,   True),
    "opp_team_k_rate":     (15.0,  35.0,  False),
    "home_away_split":     (4.0,   14.0,  False),
    "days_rest":           (3.0,   6.0,   False),     # 4-5 ideal
    "team1_runs_per_game": (3.0,   6.0,   False),
    "team2_runs_per_game": (3.0,   6.0,   False),
    "wind_factor":         (-0.5,  0.5,   False),
    "bullpen_fatigue":     (0.0,   15.0,  False),     # more fatigue = more O runs
    "hr_per_9":            (0.5,   2.0,   True),      # for pitcher props
}

_PROP_WEIGHTS: dict[str, dict[str, float]] = {
    "hits":        config.HITS_WEIGHTS,
    "total_bases": {**config.HITS_WEIGHTS, "barrel_pct": 0.15, "hard_hit_pct": 0.10},
    "home_runs":   config.HR_WEIGHTS,
    "pitcher_ks":  config.PITCHER_K_WEIGHTS,
    "game_total":  config.TOTALS_WEIGHTS,
}


def score(
    signals: dict[str, float],
    prop_type: PropType,
    line: float | None = None,
    projected_value: float | None = None,
) -> ScoreResult:
    """
    Score a set of signals and produce a confidence score and recommendation.

    Args:
        signals:          Dict of signal_name → raw numeric value
        prop_type:        One of "hits", "total_bases", "home_runs",
                          "pitcher_ks", "game_total"
        line:             The posted prop line (for game_total comparison)
        projected_value:  Optional model projection (e.g., from totals_model)

    Returns:
        ScoreResult with confidence (0–100), recommendation, and reasoning.
    """
    weights = _PROP_WEIGHTS.get(prop_type, {})
    if not weights:
        log.warning(f"No weight map for prop_type={prop_type}, returning 50.")
        return ScoreResult(prop_type, 50.0, 50, "NO PLAY", ["Unknown prop type."])

    normalized: dict[str, float] = {}
    contributions: dict[str, float] = {}
    reasoning: list[str] = []

    total_weight = 0.0
    weighted_sum = 0.0

    for signal_name, weight in weights.items():
        raw = signals.get(signal_name)
        if raw is None:
            continue

        n = _normalize(signal_name, raw)
        normalized[signal_name] = n
        contribution = n * weight
        contributions[signal_name] = round(contribution, 4)
        weighted_sum += contribution
        total_weight += weight

        reasoning.append(_explain_signal(signal_name, raw, n))

    # Rescale to [0, 1] (weighted_sum is in [-1, +1])
    if total_weight > 0:
        normalized_sum = weighted_sum / total_weight   # still in [-1, +1]
    else:
        normalized_sum = 0.0

    # Map to [0, 100]: 0 = strong under, 50 = neutral, 100 = strong over
    raw_score = 50.0 + normalized_sum * 50.0

    # If we have a projected value vs line, blend that in
    if projected_value is not None and line is not None and line > 0:
        # Logistic-style boost: larger discrepancies provide diminishing returns
        diff_pct = (projected_value - line) / line
        # Map diff_pct to a boost in [-1, 1]
        # e.g. 20% diff -> ~0.5 boost
        proj_boost = float(np.tanh(diff_pct * 3.0)) 
        
        # Blend: 70% signal-based, 30% projection-based
        raw_score = raw_score * 0.7 + (50.0 + proj_boost * 50.0) * 0.3
        
        direction_label = "over" if diff_pct > 0 else "under"
        reasoning.append(
            f"📊 Projected {projected_value:.2f} vs line {line:.1f} "
            f"({direction_label} by {abs(diff_pct)*100:.1f}%)"
        )

    # Apply confidence cap
    raw_score = float(np.clip(raw_score, 100 - config.MAX_CONFIDENCE, config.MAX_CONFIDENCE))
    confidence = int(round(raw_score))

    # Determine recommendation
    if confidence >= 50 + (config.MIN_CONFIDENCE - 50):
        recommendation: Recommendation = "OVER"
    elif confidence <= 50 - (config.MIN_CONFIDENCE - 50):
        recommendation = "UNDER"
    else:
        recommendation = "NO PLAY"

    return ScoreResult(
        prop_type=prop_type,
        raw_score=raw_score,
        confidence=confidence,
        recommendation=recommendation,
        reasoning=reasoning,
        signal_contributions=contributions,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _normalize(signal_name: str, raw: float) -> float:
    """Normalize a raw signal value to [-1, +1] using known ranges."""
    entry = _SIGNAL_RANGES.get(signal_name)
    if entry is None:
        # Unknown signal: clip to [-1, 1]
        return float(np.clip(raw, -1.0, 1.0))

    lo, hi, invert = entry
    if hi == lo:
        return 0.0
    normalized = (raw - lo) / (hi - lo) * 2 - 1   # maps [lo,hi] → [-1,+1]
    normalized = float(np.clip(normalized, -1.0, 1.0))
    return -normalized if invert else normalized


def _explain_signal(name: str, raw: float, normalized: float) -> str:
    """Return a human-readable bullet for a signal."""
    direction = "✅" if normalized > 0.1 else ("❌" if normalized < -0.1 else "➖")
    labels = {
        "rolling_avg_7": f"7-day AVG: {raw:.3f}",
        "rolling_avg_14": f"14-day AVG: {raw:.3f}",
        "rolling_avg_30": f"30-day AVG: {raw:.3f}",
        "handedness_split": f"Handedness AVG: {raw:.3f}",
        "park_hit_factor": f"Park hit factor: {raw:.2f}x",
        "park_hr_factor": f"Park HR factor: {raw:.2f}x",
        "park_run_factor": f"Park run factor: {raw:.2f}x",
        "opp_pitcher_k_pct": f"Opp pitcher K%: {raw:.1f}%",
        "barrel_pct": f"Barrel%: {raw:.1f}%",
        "hard_hit_pct": f"Hard-hit%: {raw:.1f}%",
        "fly_ball_pct": f"Fly ball%: {raw:.1f}%",
        "opp_hr_per_9": f"Opp pitcher HR/9: {raw:.2f}",
        "wind_boost": f"Wind boost: {raw:+.3f}",
        "k_per_9": f"K/9: {raw:.1f}",
        "k_pct": f"K%: {raw:.1f}%",
        "whiff_rate": f"Whiff rate: {raw:.1f}%",
        "xfip": f"xFIP: {raw:.2f}",
        "opp_team_k_rate": f"Opp team K%: {raw:.1f}%",
        "team1_runs_per_game": f"Home team R/G: {raw:.2f}",
        "team2_runs_per_game": f"Away team R/G: {raw:.2f}",
        "bullpen_fatigue": f"Bullpen fatigue: {raw:.1f} IP",
        "days_rest": f"Days rest: {int(raw)}",
    }
    label = labels.get(name, f"{name}: {raw:.3f}")
    return f"{direction} {label}"
