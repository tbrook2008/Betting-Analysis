# MLB Betting Analysis | Project Status — March 30, 2026

## 🎯 Current Strategy: The EV Quantitative Overhaul
The system has fully transitioned from a simple high-variance "Home Run" model to an **Expected Value (EV) Quantitative Trading Engine** built explicitly to exploit PrizePicks payouts and prop correlations.

### Core Pillars:
1. **Correlation Mathematics**: Evaluating whether legs share a positive correlation (Hitters from same game) or negative (Pitcher Ks vs opposing Hitters Hits).
2. **Kelly Criterion Bankroll Protection**: Auto-sizing plays utilizing fractional Kelly formulas based on true estimated EV to prevent risk-of-ruin drawdowns.
3. **Binomial Distributions**: Leveraging statistical permutations (`scipy.special.comb`) to determine the exact Expected Value of 3, 4, 5, and 6-leg Flex combinations.
4. **Historical Backtesting**: Embedded capabilities across SQLite bounds and `matplotlib` generation to measure performance against a historical data matrix.

## 🧠 System Architecture

| Component | Responsibility |
| :--- | :--- |
| **`analysis/correlation_engine.py`** | Multiplies independent leg probabilities based on intra-game dependency rules. |
| **`analysis/ev_calculator.py`** | Derives exact Expected Value based on PrizePicks standard multiplier payouts. |
| **`picks/entry_optimizer.py`** | Scans all available Top Picks combinatorics to group them into highest-EV portfolios. |
| **`tracking/bankroll_manager.py`** | Re-scales the entry sizes based on the user's `$28.00` bankroll and risk-limits. |
| **`tracking/performance_tracker.py`** | The SQLite local database tracking every generated play. |
| **`utils/demo_mode.py`** | The backtesting interface generating return-on-investment charts. |

## 📈 Performance Summary
- **Current Balance**: $28.00 
- **System Version**: v2.1 (EV/PP Focus)
- **Pending Actions**: Daily slate crunch currently executing to maximize PP return.

## 🛠️ CLI Architecture (`click`)
- **`python main.py run --bankroll 28 --risk conservative`**: Generate max EV portfolio for today.
- **`python main.py grade --date 2026-03-30`**: Resolve all pending plays against actual outcomes.
- **`python main.py stats`**: Fetch DB returns.
- **`python main.py backtest --start-date 2026-03-01 --end-date 2026-03-30`**: Visualize model performance.
