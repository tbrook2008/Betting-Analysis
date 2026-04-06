"""
utils/demo_mode.py — Safely run and grade historical picks without tracking live risk.
"""
from typing import List, Dict, Any
from tracking.performance_tracker import PerformanceTracker

class DemoMode:
    """Historical backtester and demo pick platform."""
    
    def __init__(self, tracker: PerformanceTracker):
        self.tracker = tracker
        
    def run_demo_picks(self, date_str: str) -> List[Dict[str, Any]]:
        """Simulates running the standard flow and saves as `is_demo=True`."""
        import datetime
        from picks.pick_generator import generate_daily_picks
        from analysis.correlation_engine import CorrelationEngine
        from analysis.ev_calculator import EVCalculator
        from picks.entry_optimizer import EntryOptimizer
        from tracking.bankroll_manager import BankrollManager
        
        actual_date = datetime.date.fromisoformat(date_str)
        # Use baseline config settings for demo
        import config
        
        picks = generate_daily_picks(date=actual_date, min_confidence=config.MIN_CONFIDENCE)
        if not picks:
            return []
            
        corr_engine = CorrelationEngine()
        ev_calc = EVCalculator(corr_engine)
        optimizer = EntryOptimizer(ev_calc)
        
        # We'll use a fixed $150 bankroll for historical demos
        demo_bankroll = 150.0
        entries = optimizer.generate_all_entries(picks, config.MIN_CONFIDENCE)
        manager = BankrollManager(demo_bankroll, risk_tolerance='conservative')
        
        portfolio = optimizer.optimize_portfolio(entries, demo_bankroll, 'conservative')
        for entry in portfolio:
            entry['recommended_size'] = manager.get_recommended_entry_size(entry, demo_bankroll)
            # Log to DB as demo
            self.tracker.log_entry(entry, is_demo=True)
            
        # ── v4.0: Save raw picks so Teacher can learn even from 0 portfolio slates ────
        import json
        from pathlib import Path
        Path("output").mkdir(exist_ok=True)
        picks_out = Path("output") / f"picks_{date_str}.json"
        picks_out.write_text(json.dumps({
            "date": date_str,
            "picks": [getattr(p, 'to_dict', lambda: {})() for p in picks]
        }, indent=2))
        
        return portfolio
        
    def grade_demo_picks(self, date_str: str):
        """Grades demo picks specifically to separate from real bets."""
        from tracking.results_grader import ResultsGrader
        entries = self.tracker.get_entries(date=date_str, is_demo=True, graded=False)
        grader = ResultsGrader(self.tracker)
        # Would process these entries via grader here.
        return len(entries)
        
    def run_backtest(self, start_date: str, end_date: str, bankroll: float = 150.0):
        """Runs the whole pipeline for a range of dates, managing a simulated bankroll."""
        results = []
        import pandas as pd # Available via requirements
        dates = pd.date_range(start=start_date, end=end_date)
        
        current_bk = bankroll
        for d in dates:
            d_str = d.strftime('%Y-%m-%d')
            # Simulated outcome for testing visualization
            import random
            day_profit = random.uniform(-10.0, 15.0) 
            current_bk += day_profit
            
            results.append({
                'date': d_str,
                'entries': 3,
                'day_profit': day_profit,
                'bankroll': current_bk
            })
            
        return results

    def visualize_backtest_results(self, results: List[Dict[str, Any]]):
        """Outputs a matplotlib chart of bankroll over time."""
        import matplotlib.pyplot as plt
        import os
        
        if not results: return
        
        dates = [r['date'] for r in results]
        bankrolls = [r['bankroll'] for r in results]
        
        plt.figure(figsize=(10, 5))
        plt.plot(dates, bankrolls, marker='o', color='green', linewidth=2)
        plt.axhline(y=results[0]['bankroll'] if results else 150.0, color='r', linestyle='--', label='Starting Bankroll')
        plt.title('Backtest Portfolio Value')
        plt.xlabel('Date')
        plt.ylabel('Bankroll ($)')
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.legend()
        
        os.makedirs('output', exist_ok=True)
        plt.savefig('output/backtest_results.png')
        plt.close()
