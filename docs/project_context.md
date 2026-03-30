# MLB Betting Analysis | Project Status — March 30, 2026

## 🎯 Current Strategy: "The Stability Pivot"
The system has fully transitioned from a high-variance "Home Run" model to a **Stability-Weighted** strategy. 

### Core Pillars:
1. **The 0.5 Line Safety**: Preference for Hit/Single props with a 0.5 line score, providing the lowest possible variance for hitters.
2. **Gold Standard K-Metrics**: Preference for pitchers with >30% strikeout rates (e.g. Cole Ragans, Chris Sale, Chase Burns).
3. **Autonomous Learning**: The system now features a **Teacher Module** that reviews yesterday's results and self-adjusts its confidence weights daily.

## 🧠 System Architecture

| Component | Responsibility |
| :--- | :--- |
| **`analysis/teacher.py`** | The "Brain." Runs every morning to grade accuracy and tune model multipliers. |
| **`analysis/confidence_scorer.py`** | The "Executioner." Applies variance penalties, stability bonuses (Gold Standard), and AI learned multipliers. |
| **`picks/parlay_builder.py`** | The "Orchestrator." Groups high-confidence legs into 2-leg Power Plays and 3-leg Flex Plays. |
| **`data/dynamic_weights.json`** | The "Memory." Persists the AI's learned adjustments across runs. |

## 📈 Performance Summary
- **Initial Deposit**: $30.00
- **Current Balance**: $28.00 (from a $28.00 3-leg Flex Win on 03/28)
- **Pending Entries**: $28.00 spread across a $20 3-leg Power Play and an $8 2-leg Power Play for 03/30.

## 🛠️ Maintenance & CLI
- **`python main.py run`**: Automatic learning triggered on first run of the day.
- **`python main.py reset-learning`**: Wipes all AI multipliers back to 1.0 baseline.
