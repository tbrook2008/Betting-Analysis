# AI Betting Analysis | Project Status — April 17, 2026 (v6.0 Arena/NBA Engine)

## 🎯 Current Strategy: Multi-Sport Arena Floor Engine
The system has been upgraded to **"v6.0"** to address the realities of tournament-style DFS platforms (PrizePicks Pick 'Em Arena). The engine now uses exclusively **"Arena Minimum Guarantee"** payouts for EV calculations, completely ignoring the variance of "1st Place" payouts. Furthermore, the engine has been horizontally expanded to support NBA markets via the `nba_api`.

### Core Architecture Pillars:
1. **Multi-Sport Routing (`picks/pick_generator.py`)**: Supports `--sport mlb` and `--sport nba` dynamically.
2. **Arena Floor Math (`analysis/ev_calculator.py`)**: Calculates exact binomial EV relying *only* on the Minimum Guarantees (e.g., 4X for 5-Flex, 27X for 6-Flex).
3. **NBA Predictive Models (`analysis/nba_models.py`)**: Trailing momentum and season baseline models for Points, Rebounds, Assists, and PRA.
4. **Correlation Mathematics (`analysis/correlation_engine.py`)**: Mathematically scales independent probabilities with Game Script Stack bonuses.
5. **Kelly Criterion + Streak Staking (`tracking/bankroll_manager.py`)**: Win-Streak Progressive Staking and Fibonacci Strategy.
6. **Market Edge Signal (`analysis/confidence_scorer.py`)**: Multi-book consensus validation signal for every line.
5. **Weather Intelligence (`data/weather_client.py`)**: Injects wind speed/direction and temperature signals into the Hits model.
6. **Lineup Intelligence (`data/lineup_client.py`)**: Blocks entries for players not in the starting lineup or those at the bottom (7-9) of the batting order.
7. **The Teacher (`analysis/teacher.py`)**: Autonomous accuracy feedback loop tuning `dynamic_weights.json` daily.

## 🧠 System Index

| Component | Responsibility |
| :--- | :--- |
| **`analysis/teacher.py`** | The autonomous nervous system that degrades or amplifies model weight arrays based on the empirical hit-rate calculated from yesterday's MLB server outputs. |
| **`analysis/correlation_engine.py`** | Multiplies independent leg probabilities based on intra-game dependency rules. |
| **`analysis/ev_calculator.py`** | Derives exact Expected Value based on PrizePicks standard multiplier payouts. |
| **`picks/entry_optimizer.py`** | Flex-6 first portfolio builder. Runs quality gate (≥5 of 6 legs at 85%+ confidence) before including any 6-leg combo. Suppresses Power-2/3 entries when prefer_flex=True. |
| **`data/mlb_client.py`** | Aggregates massive live MLB boxscore dictionaries to avoid missing cache logs. |
| **`tracking/bankroll_manager.py`** | Entry-type-aware Kelly sizing. Re-scales entry sizes based on format profitability history. |
| **`tracking/performance_tracker.py`** | SQLite backend storing every generated play. |

## 📈 Performance & State Summary
- **Current Balance**: $186.97 (started $150.00)
- **Hypothetical $100 Journey**: +$26.97 (+27%) as of April 8
- **System Version**: v5.1 (ROI-Hardened Engine)
- **Active State**: All 10 critical profit improvements implemented and verified.

## 🛠️ CLI Architecture (`click`)
- **`python main.py run --bankroll 30 --risk conservative`**: Generates and optimizes max EV portfolio for today.
- **`python main.py grade --date 2026-03-30`**: Resolves all pending plays against actual MLB boxscore outcomes and activates the `Teacher`.
- **`python main.py stats`**: Fetch SQL DB returns.
- **`python main.py backtest --start-date 2026-03-01 --end-date 2026-03-30`**: Visually maps historically predicted models.

## 🔧 v5.1 Improvements (April 8, 2026) — ROI-Hardened Engine

| # | Fix | File | What Changed |
|---|-----|------|--------------|
| 8 | **Flex-6 Priority** | `picks/entry_optimizer.py` | Optimizer now always builds a Flex-6 entry first. 5-leg and 6-leg entries are forced to Flex format. Power-2/3 entries suppressed in conservative mode. |
| 9 | **Conditional Kelly Sizing** | `tracking/bankroll_manager.py` | Flex-6/5 capped at 20% of bankroll. Flex-3/4 at 12%. All Power entries hard-capped at 5%. Allocation matches historical profitability per format. |
| 10 | **6-Leg Quality Gate** | `picks/entry_optimizer.py` | Six-leg combos require ≥5 legs at 85%+ confidence. Prevents weak-leg dilution (e.g. Apr 6 Alvarez failure that broke a 5/6 entry). |

## 🔧 v5.0 Improvements (April 6, 2026) — Wide-Scope Expansion

| # | Fix | File | What Changed |
|---|-----|------|--------------|
| - | **Odds API Refactor** | `data/draftkings_scraper.py` | Switched to `/events/{eventId}/odds` endpoint. Parallelized fetching eliminates 422 errors. |
| - | **Market Edge Signal** | `analysis/confidence_scorer.py` | DraftKings implied probability used as confidence modifier. |
| - | **Statcast Hits Model** | `analysis/hits_model.py` | Hard-Hit% and Barrel% added as signals. `mlb_client.py` game log parsing fixed. |
| - | **Prop Coverage** | `picks/pick_generator.py` | Added Hits, Runs, RBIs, Total Bases, and Pitcher Ks to active prop map. |
| - | **Threshold Balanced** | `config.py` | `min_confidence_threshold` set to 58% for optimal diversity. |

## 🚀 Recommended Next Steps
1. **Fibonacci Stake Progression**: On winning streaks, increase daily stake by a fixed multiplier to exploit hot model runs.
2. **Cross-Platform Arbitrage**: Add FanDuel / Underdog lines to detect pricing inefficiencies vs PrizePicks.
3. **Pitcher-vs-Batter ML Module**: Build matchup-specific models using Statcast spin rates and plate discipline metrics.
4. **React/FastAPI Dashboard**: Real-time bankroll chart, daily pick table, and Teacher learning history visualization.
5. **Rolling Backtest Engine**: Weekly automated backtest to continuously validate model accuracy as the season progresses.
