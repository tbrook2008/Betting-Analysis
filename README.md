# MLB Betting Analysis 🏟️

A fully automated Python system for MLB prop betting — ingests real game data, scores each PrizePicks/DraftKings line with a weighted confidence model, and surfaces high-confidence picks + parlays via CLI or REST API.

---

## Quick Start

```bash
# 1. Create + activate a virtual environment
python3 -m venv .venv && source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy env template and add your keys
cp .env.example .env
# Optional: add ODDS_API_KEY for DraftKings lines

# 4. Run picks for today
python main.py run

# 5. Start the REST API
python main.py serve
# → http://localhost:8000/docs
```

---

## The Advanced CLI (Powered by click)

The system is fully controlled via a modular set of commands.

```bash
# 1. Generate optimal Positive EV portfolios for today:
python main.py run --bankroll 150 --risk conservative 

# 2. Grade yesterday's portfolio via MLB stats and adjust trackers:
python main.py grade --date 2026-03-30

# 3. Simulate a one-month historical backtest
python main.py backtest --start-date 2026-03-01 --end-date 2026-03-30 --bankroll 150

# 4. Read lifetime algorithm profitability
python main.py stats

# 5. Start API Server or reset AI weights
python main.py serve --port 8080
python main.py reset-learning
```

---

## REST API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/picks` | All picks for today |
| GET | `/picks?date=2025-04-15&min_confidence=65` | Filtered picks |
| GET | `/picks/player/{name}` | Picks for a specific player |
| GET | `/parlays` | Top Power Play + Flex Play parlays |
| GET | `/lines/prizepicks` | Raw PrizePicks lines |
| GET | `/lines/draftkings` | Raw DraftKings lines |
| GET | `/lines/compare/{player}?prop_type=Hits` | Line comparison |
| POST | `/cache/clear` | Bust all caches |
| GET | `/health` | Health check |

Full interactive docs at **http://localhost:8000/docs**

---

| Source | What it provides | Key needed? |
|---|---|---|
| MLB Stats API (`statsapi`) | Schedule, game logs, season stats, splits | ❌ Free |
| Statcast via `pybaseball` | Barrel%, hard hit%, xFIP, whiff rate, K% | ❌ Free |
| PrizePicks Partner API | Player prop lines | ❌ Free (semi-public) |
| The Odds API | DraftKings player prop lines + American odds | ✅ `ODDS_API_KEY` |
| OpenWeatherMap | Live wind speed/direction for HR boost | 🟢 `OWM_API_KEY` (Optional) |

---

## Project Structure

```
Betting Analysis/
├── config.py              # Tunable weights, thresholds, park factors
├── main.py                # CLI entry point
├── scheduler.py           # APScheduler daily runner
│
├── data/
│   ├── mlb_client.py      # MLB Stats API + Statcast wrappers
│   ├── prizepicks_scraper.py
│   └── draftkings_scraper.py
│
├── analysis/
│   ├── teacher.py         # 🧠 The Brain: Autonomous daily learning
│   ├── hits_model.py      # Hits / Total Bases signals
│   ├── hr_model.py        # Home Run signals
│   ├── pitcher_model.py   # Pitcher Strikeout signals
│   ├── totals_model.py    # Game Total signals
│   └── confidence_scorer.py  # Weighted 0–100 scoring engine
│
├── picks/
│   ├── pick_generator.py  # Full pipeline orchestrator
│   └── parlay_builder.py  # Correlation-aware parlay builder
│
├── api/
│   ├── app.py             # FastAPI factory
│   └── routes.py          # All endpoints
│
├── utils/
│   ├── logger.py          # Rich logger
│   ├── cache.py           # diskcache decorator
│   └── http.py            # HTTP client with retry logic
│
├── tests/                 # Pytest suite
│   └── test_confidence_scorer.py
│
├── output/                # JSON pick files written here
└── .cache/                # diskcache directory (ignored)
```

---

## Confidence Scoring

Each prop runs through a **signal → normalize → weight → score** pipeline:

1. **Signals** are fetched for the prop type (AVG, K%, barrel%, etc.)
2. Each signal is **normalized to [-1, +1]** against known MLB ranges
3. Signals are **weighted** by prop-type-specific dictionaries in `config.py`
4. The weighted sum maps to a **0–100 score** (50 = neutral, 70+ = high confidence)
5. **Quantitative EV Optimization**: Rebuilt to calculate exact statistical edge. `analysis/ev_calculator` uses binomial theorems (`scipy`) and correlation multipliers (`analysis/correlation_engine.py`) to build combinations that explicitly target positive ROI rather than raw hit-rate.
6. **Dynamic Entry Generation**: Uses permutations (`picks/entry_optimizer.py`) to locate up to $150 Bankroll across fractional Kelly Criterion sized entries, safeguarding against drawdowns.
7. **SQLite Backtesting DB**: Auto-logs and grades real-time entries in `tracking/performance.db` for complete P&L analytics.
8. **Agentic Teacher & Re-scorer**: Scrapes results to train `data/dynamic_weights.json` on the first run of the day to recalibrate its confidence margins. AI automatically applies a **Dynamic Multiplier** (capped at ±10%) to today's confidence scores.
9. **PrizePicks Placement Compliance**: Strict filtering protocols naturally exclude duplicated players within the same entry and mandates properties from two or more unique teams to guarantee line placement eligibility. Home Runs are banned programmatically due to excessive variance.

View the AI's current memory and multipliers in `data/dynamic_weights.json`.

---

## Output Format

`output/picks_YYYY-MM-DD.json`:

```json
{
  "date": "2025-04-15",
  "picks_count": 12,
  "picks": [
    {
      "player_name": "Aaron Judge",
      "prop_type": "Home Runs",
      "line": 0.5,
      "recommendation": "OVER",
      "confidence": 78,
      "reasoning": ["✅ Barrel%: 22.4%", "✅ Opp pitcher HR/9: 1.82", "✅ Park HR factor: 1.16x"],
      "source": "PrizePicks"
    }
  ],
  "parlays": {
    "power_plays": [...],
    "flex_plays": [...]
  }
}
```
