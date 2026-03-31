"""
tracking/results_grader.py — Auto-grades pending entries based on real MLB results.
"""
import datetime
from typing import List, Dict, Any
from tracking.performance_tracker import PerformanceTracker
from analysis.teacher import Teacher

class ResultsGrader:
    def __init__(self, tracker: PerformanceTracker):
        self.tracker = tracker
        self.teacher = Teacher()
        
    def _map_prop_to_category(self, prop_type: str) -> str:
        s = prop_type.lower()
        if "pitcher" in s and "strikeout" in s:
            return "pitcher_ks"
        if "home run" in s:
            return "home_runs"
        if "total base" in s:
            return "total_bases"
        if "single" in s:
            return "singles"
        if "hit" in s: 
            return "hits"
        return "hits" # fallback
        
    def _fetch_actual_result(self, pick: Any, date_str: str) -> float:
        """Queries true stats via Teacher method."""
        cat = self._map_prop_to_category(getattr(pick, 'prop_type', ''))
        player_name = getattr(pick, 'player_name', '')
        
        # Parse date specifically matching ISO but extracting just date
        dt = datetime.datetime.fromisoformat(date_str).date()
        
        res = self.teacher._get_result(player_name, dt, cat)
        if res is not None:
            return res
            
        return -1.0
        
    def grade_date(self, date_str: str):
        """Finds all ungraded entries for a date and grades them."""
        entries = self.tracker.get_entries(date=date_str, graded=False)
        
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
                
                if actual == -1.0:
                    results.append('miss')
                    continue
                    
                if over_under == 'OVER':
                    hit = actual > line
                else:
                    hit = actual < line
                    
                results.append('hit' if hit else 'miss')
                
            entry_type = entry.get('entry_type', 'power_2')
            mult = payouts.get(entry_type, 0.0)
            
            self.tracker.grade_entry(entry['entry_id'], results, mult)
            graded_count += 1
            
        if graded_count > 0:
            dt = datetime.datetime.fromisoformat(date_str).date()
            try:
                self.teacher.run_daily_retro(dt)
            except Exception as e:
                # Catch parsing errors if older picks format deviates
                pass
                
        return graded_count
