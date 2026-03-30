"""
tracking/results_grader.py — Auto-grades pending entries based on real MLB results.
"""
from typing import List, Dict, Any
from tracking.performance_tracker import PerformanceTracker

class ResultsGrader:
    def __init__(self, tracker: PerformanceTracker):
        self.tracker = tracker
        
    def _fetch_actual_result(self, pick: Any, date_str: str) -> float:
        """Mock method: In production, this queries mlb_client for actual player stat."""
        # For Phase 3 boilerplate structure, returning a mock value.
        line = getattr(pick, 'line', 0.5)
        return line + 1.0 # Mocks a win. To be replaced with data.mlb_client logic
        
    def grade_date(self, date_str: str):
        """Finds all ungraded entries for a date and grades them."""
        entries = self.tracker.get_entries(date=date_str, graded=False)
        
        # Standard PrizePicks payout mapping
        payouts = {
            'power_2': 3.0, 'power_3': 5.0, 'power_4': 10.0, 'power_5': 20.0, 'power_6': 25.0,
            'flex_3': 2.25, 'flex_4': 5.0, 'flex_5': 10.0, 'flex_6': 25.0
        }
        
        graded_count = 0
        for entry in entries:
            results = []
            for pick in entry['picks']:
                actual = self._fetch_actual_result(pick, date_str)
                line = getattr(pick, 'line', 0.5)
                over_under = getattr(pick, 'over_under', 'OVER')
                
                if over_under == 'OVER':
                    hit = actual > line
                else:
                    hit = actual < line
                    
                results.append('hit' if hit else 'miss')
                
            entry_type = entry.get('entry_type', 'power_2')
            mult = payouts.get(entry_type, 0.0)
            
            self.tracker.grade_entry(entry['entry_id'], results, mult)
            graded_count += 1
            
        return graded_count
