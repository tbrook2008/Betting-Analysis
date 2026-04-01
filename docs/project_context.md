# MLB Betting Analysis | Project Status — April 01, 2026

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
- **System Version**: v3.0 (Autonomous EV Engine)
- **Active State**: The engine generated a Flex 3 ticket focused exclusively on `pitcher_ks` to mitigate the AI's recent downgraded `home_runs` multiplier. After games concluded, `results_grader.py` evaluated the entry natively against MLB live box scores and cleanly generated a fractional Flex-3 rule loss (`-$1.50` off a `$3.00` wager) verifying the `BankrollManager` and DB handle partial PrizePicks flex payouts perfectly without failure.

## 🛠️ CLI Architecture (`click`)
- **`python main.py run --bankroll 30 --risk conservative`**: Generates and optimizes max EV portfolio for today.
- **`python main.py grade --date 2026-03-30`**: Resolves all pending plays against actual MLB boxscore outcomes and activates the `Teacher`.
- **`python main.py stats`**: Fetch SQL DB returns.
- **`python main.py backtest --start-date 2026-03-01 --end-date 2026-03-30`**: Visually maps historically predicted models.

## 🚀 Recommended Agent Pivot / Next Steps
1. **Sportsbook Arbitration Surface**: Hard-code Fanduel or Underdog SDKs into the baseline odds extraction to expand the arbitrage surface layer.
2. **React/FastAPI Dashboard**: Wrap the SQLite SQL performance tracking into a visualization grid, showing the daily ROI compound graph over time.
3. **Advanced ML Models**: Build deeper neural splits to track individual batter success directly against individual pitcher spin rates, feeding that into a new `analysis/advanced_model.py`.
