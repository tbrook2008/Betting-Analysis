# MLB Betting Analysis | Project Status — April 01, 2026 (v4.0)

## 🎯 Current Strategy: The Autonomous Quantitative Engine
The system has fully transitioned from a simple high-variance model to a self-teaching **Expected Value (EV) Quantitative Trading Engine** built explicitly to exploit PrizePicks payouts and mathematically react to its own failures.

### Core Architecture Pillars:
1. **Correlation Mathematics (`analysis/correlation_engine.py`)**: Mathematically scales independent probabilities into reliant permutations (e.g. boosting the probability if a ticket pairs batters from the same game).
2. **Binomial Distributions (`analysis/ev_calculator.py`)**: Utilizes statistical combinatorics (`scipy.special.comb`) to determine the exact Expected Value and ROIs of 3, 4, 5, and 6-leg combinations hitting the threshold (N or N-1).
3. **Kelly Criterion Bankroll Protection (`tracking/bankroll_manager.py`)**: Autosizing entry plays leveraging fractional Kelly formulas to eliminate risk-of-ruin while compounding daily returns.
4. **Live Verification (`tracking/results_grader.py`)**: The system no longer mocks data. It systematically scrapes the live MLB API (`statsapi.boxscore_data`) each morning to fetch explicit outcomes for graded tickets.
5. **The Teacher (`analysis/teacher.py`)**: *The active AI feedback loop.* After verifying MLB box scores, the Teacher checks its accuracy. If the AI missed its projections on a specific prop type (e.g., Home Runs), the algorithm dynamically nerfs its confidence multiplier for that prop in `dynamic_weights.json` so it scales back risk mechanically going forward.

## 🧠 System Index

| Component | Responsibility |
| :--- | :--- |
| **`analysis/teacher.py`** | The autonomous nervous system that degrades or amplifies model weight arrays based on the empirical hit-rate calculated from yesterday's MLB server outputs. |
| **`analysis/correlation_engine.py`** | Multiplies independent leg probabilities based on intra-game dependency rules. |
| **`analysis/ev_calculator.py`** | Derives exact Expected Value based on PrizePicks standard multiplier payouts. |
| **`picks/entry_optimizer.py`** | Scans all available Top Picks combinatorics to group them into highest-EV portfolios, mandating strict compliance features (no dupes, multi-team rules). |
| **`data/mlb_client.py`** | Aggregates massive live MLB boxscore dictionaries to avoid missing cache logs. |
| **`tracking/bankroll_manager.py`** | Re-scales the entry sizes based on the user's localized bankroll and risk exposure. |
| **`tracking/performance_tracker.py`** | SQLite backend storing every generated play. |

## 📈 Performance & State Summary
- **Current Balance**: $28.50
- **System Version**: v4.0 (Profit-Hardened Engine)
- **Active State**: System has been audited and all 7 identified critical/high-impact profit gaps have been patched. See improvements section below.

## 🛠️ CLI Architecture (`click`)
- **`python main.py run --bankroll 30 --risk conservative`**: Generates and optimizes max EV portfolio for today.
- **`python main.py grade --date 2026-03-30`**: Resolves all pending plays against actual MLB boxscore outcomes and activates the `Teacher`.
- **`python main.py stats`**: Fetch SQL DB returns.
- **`python main.py backtest --start-date 2026-03-01 --end-date 2026-03-30`**: Visually maps historically predicted models.

## 🔧 v4.0 Profit Improvements (April 1, 2026)

| # | Fix | File | What Changed |
|---|-----|------|--------------|
| 1 | **Proportional Teacher Nudge** | `analysis/teacher.py` | Replaced flat ±2% accuracy signal with a proportional formula: `nudge = (accuracy - 0.55) * 0.10`. A 6% hit-rate now triggers a ~4.9% penalty rather than 2%. |
| 2 | **Full Correlation Rules** | `analysis/correlation_engine.py` | Wired all 6 correlation rules. Pitcher vs opposing team batters now correctly scores **−0.35**. Same-game pitchers score **−0.20**. Was always returning 0.0 before. |
| 3 | **Correct Flex Partial Payouts** | `analysis/ev_calculator.py` | Replaced single payout multiplier with per-outcome binomial mapping. Flex 3: 3/3=2.25x, 2/3=1.25x, 1/3=0x. Eliminates inflated EV. |
| 4 | **Live Bankroll Auto-Read** | `tracking/performance_tracker.py`, `main.py` | System now reads the real bankroll from `performance.db` P&L sum. No more manual `--bankroll` required. |
| 5 | **Line-Difficulty Penalty** | `analysis/confidence_scorer.py` | Pitcher K lines >9.0 incur a penaly of 2.5 pts per K above threshold. Hit lines >1.5 penalized 2.0 pts per unit. |
| 6 | **Market Implied Probability Filter** | `picks/entry_optimizer.py` | Picks are filtered out if model confidence does not exceed the market-implied probability by at least 5%. |
| 7 | **DB-Backed Teacher Learning** | `tracking/performance_tracker.py`, `tracking/results_grader.py` | Graded picks now persist `actual_value` and `was_correct` to `entry_picks` table. Teacher consumes verified data instead of re-fetching the API daily. |

## 🚀 Recommended Next Steps
1. **Sportsbook Arbitration Surface**: Hard-code Fanduel or Underdog SDKs to expand the arbitrage surface.
2. **React/FastAPI Dashboard**: Wrap the SQLite performance tracking into a visualization grid.
3. **Advanced ML Models**: Build pitcher-vs-batter split models using Statcast spin rates.
4. **Real-time Odds Integration**: Expose DraftKings American odds as `market_implied_prob` on each `PickResult`, enabling Fix 6 to fully activate.

