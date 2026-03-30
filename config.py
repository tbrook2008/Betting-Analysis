"""
config.py — All tunable settings for the MLB Betting Analysis system.
Adjust weights, thresholds, and constants here without touching model code.
"""
from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
CACHE_DIR = Path(os.getenv("CACHE_DIR", ".cache"))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "output"))
OUTPUT_DIR.mkdir(exist_ok=True)
CACHE_DIR.mkdir(exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# API Keys & Endpoints
# ─────────────────────────────────────────────────────────────────────────────
ODDS_API_KEY: str = os.getenv("ODDS_API_KEY", "")
ODDS_API_BASE = "https://api.the-odds-api.com/v4"
PRIZEPICKS_API_BASE = "https://partner-api.prizepicks.com"
PRIZEPICKS_MLB_LEAGUE_ID = "2"  # MLB league id on PrizePicks

OWM_API_KEY: str = os.getenv("OWM_API_KEY", "")
OWM_API_BASE = "https://api.openweathermap.org/data/2.5"

# ─────────────────────────────────────────────────────────────────────────────
# FastAPI
# ─────────────────────────────────────────────────────────────────────────────
API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
API_PORT: int = int(os.getenv("API_PORT", "8000"))

# ─────────────────────────────────────────────────────────────────────────────
# Scheduler
# ─────────────────────────────────────────────────────────────────────────────
SCHEDULER_LEAD_MINUTES: int = int(os.getenv("SCHEDULER_LEAD_MINUTES", "60"))

# ─────────────────────────────────────────────────────────────────────────────
# Confidence Scoring
# ─────────────────────────────────────────────────────────────────────────────
MIN_CONFIDENCE: int = 55          # Picks below this are filtered out
HIGH_CONFIDENCE: int = 70         # Tier used in parlay selection
MAX_CONFIDENCE: int = 95          # Cap to avoid overconfidence

# ─────────────────────────────────────────────────────────────────────────────
# Signal Weights — Hits / Total Bases Model
# ─────────────────────────────────────────────────────────────────────────────
HITS_WEIGHTS = {
    "rolling_avg_7":       0.30,
    "rolling_avg_14":      0.20,
    "rolling_avg_30":      0.10,
    "handedness_split":    0.20,
    "park_hit_factor":     0.10,
    "opp_pitcher_k_pct":   0.10,   # high K% → fewer hits → negative signal
}

# ─────────────────────────────────────────────────────────────────────────────
# Signal Weights — Home Run Model
# ─────────────────────────────────────────────────────────────────────────────
HR_WEIGHTS = {
    "barrel_pct":          0.20,   # Reduced from 0.30
    "hard_hit_pct":        0.15,   # Reduced from 0.20
    "hr_rate_30d":         0.15,   # [NEW] Recency signal
    "hr_rate_15d":         0.10,   # [NEW] Near-term surge
    "fly_ball_pct":        0.15,
    "opp_hr_per_9":        0.15,   # Reduced from 0.20
    "park_hr_factor":      0.05,
    "wind_boost":          0.05,
}

# ─────────────────────────────────────────────────────────────────────────────
# Stability & "Safe Money" Thresholds (Learning from hits)
# ─────────────────────────────────────────────────────────────────────────────
STABILITY_THRESHOLDS = {
    "pitcher_k_pct_min": 0.30,   # 30% K-rate is the "Gold Standard"
    "hitter_line_max":   0.5,    # 0.5 lines are lowest variance (one hit)
}

# ─────────────────────────────────────────────────────────────────────────────
# Variance & Reliability Scaling
# ─────────────────────────────────────────────────────────────────────────────
# Multipliers to discount confidence for high-variance events
PROP_VARIANCE_FACTORS = {
    "home_runs":   0.75,   # High variance, harder to predict day-to-day
    "hits":        0.95,   # Lower variance
    "total_bases": 0.90,
    "pitcher_ks":  0.95,
}

# ─────────────────────────────────────────────────────────────────────────────
# Signal Weights — Pitcher Strikeouts Model
# ─────────────────────────────────────────────────────────────────────────────
PITCHER_K_WEIGHTS = {
    "k_per_9":             0.25,
    "k_pct":               0.25,
    "whiff_rate":          0.20,
    "xfip":                0.10,   # lower xFIP → better pitcher → more Ks
    "opp_team_k_rate":     0.15,
    "home_away_split":     0.05,
}

# ─────────────────────────────────────────────────────────────────────────────
# Signal Weights — Game Totals Model
# ─────────────────────────────────────────────────────────────────────────────
TOTALS_WEIGHTS = {
    "team1_runs_per_game":  0.20,
    "team2_runs_per_game":  0.20,
    "starter1_xfip":        0.15,
    "starter2_xfip":        0.15,
    "park_run_factor":      0.10,
    "wind_factor":          0.10,
    "bullpen_fatigue":      0.10,
}

# ─────────────────────────────────────────────────────────────────────────────
# Park Factors (2024 baseline, 100 = neutral)
# Source: FanGraphs park factors — update each season
# ─────────────────────────────────────────────────────────────────────────────
PARK_RUN_FACTORS: dict[str, float] = {
    "Coors Field":              1.20,
    "Great American Ball Park": 1.12,
    "Fenway Park":              1.08,
    "Yankee Stadium":           1.07,
    "Chase Field":              1.06,
    "American Family Field":    1.05,
    "Globe Life Field":         1.04,
    "Truist Park":              1.03,
    "Wrigley Field":            1.02,
    "Citizens Bank Park":       1.02,
    "Minute Maid Park":         1.01,
    "Oracle Park":              0.94,
    "Petco Park":               0.93,
    "T-Mobile Park":            0.93,
    "Dodger Stadium":           0.97,
    "Kauffman Stadium":         0.96,
    "PNC Park":                 0.96,
    "Citi Field":               0.97,
    "Progressive Field":        0.98,
    "Guaranteed Rate Field":    1.00,
    "Busch Stadium":            0.98,
    "Camden Yards":             1.03,
    "Tropicana Field":          0.96,
    "loanDepot park":           0.95,
    "Target Field":             0.99,
    "Angel Stadium":            0.98,
    "Oakland Coliseum":         0.94,
    "Nationals Park":           1.00,
    "SunTrust Park":            1.01,
    "New Ballpark":             1.00,   # placeholder for any new venues
}

PARK_HR_FACTORS: dict[str, float] = {
    "Coors Field":              1.22,
    "Great American Ball Park": 1.18,
    "Yankee Stadium":           1.16,
    "Fenway Park":              1.08,
    "Chase Field":              1.10,
    "Citizens Bank Park":       1.09,
    "Globe Life Field":         1.07,
    "Oracle Park":              0.86,
    "Petco Park":               0.88,
    "T-Mobile Park":            0.90,
    "Dodger Stadium":           0.95,
    "PNC Park":                 0.93,
}

# ─────────────────────────────────────────────────────────────────────────────
# Statcast Normalization Ranges (for signal normalization to [-1, +1])
# ─────────────────────────────────────────────────────────────────────────────
BARREL_PCT_RANGE = (0.0, 25.0)       # league range of barrel%
HARD_HIT_PCT_RANGE = (20.0, 60.0)
FLY_BALL_PCT_RANGE = (15.0, 55.0)
K_PER_9_RANGE = (4.0, 14.0)
K_PCT_RANGE = (10.0, 40.0)
WHIFF_RATE_RANGE = (15.0, 45.0)
XFIP_RANGE = (2.5, 6.5)             # lower is better
HR_PER_9_RANGE = (0.5, 2.5)         # for opposing pitcher
OPP_K_RATE_RANGE = (15.0, 35.0)

# ─────────────────────────────────────────────────────────────────────────────
# Parlay Builder
# ─────────────────────────────────────────────────────────────────────────────
PARLAY_MIN_LEGS = 2
PARLAY_MAX_LEGS = 5
PARLAY_SAME_GAME_PENALTY = 0.3      # correlation penalty for same-game legs
PARLAY_SAME_TEAM_PENALTY = 0.15     # correlation penalty for same-team legs

# ─────────────────────────────────────────────────────────────────────────────
# Cache TTLs (seconds)
# ─────────────────────────────────────────────────────────────────────────────
CACHE_TTL_LINES = 3_600        # 1 hour  — live betting lines
CACHE_TTL_STATCAST = 21_600    # 6 hours — Statcast data
CACHE_TTL_SCHEDULE = 3_600     # 1 hour  — game schedule
CACHE_TTL_GAME_LOGS = 21_600   # 6 hours — player game logs

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
