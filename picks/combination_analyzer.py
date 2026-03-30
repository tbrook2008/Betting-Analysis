"""
picks/combination_analyzer.py — Detects overlapping picks and negative correlations.
"""
from typing import List, Any

class CombinationAnalyzer:
    """Helper methods for resolving conflicts between picks and combinations."""
    
    def __init__(self):
        pass
        
    def has_strong_negative_correlation(self, picks_list: List[Any], threshold: float = -0.3) -> bool:
        """Determines if any two picks exhibit strong negative correlation (e.g. Under K vs Over Hits same game)."""
        # Simplified placeholder for structural negative correlation blocking
        return False
        
    def get_overlap_score(self, picks_list1: List[Any], picks_list2: List[Any]) -> float:
        """Returns % of overlap between two combinations."""
        set1 = {f"{getattr(p, 'player_name', '')}_{getattr(p, 'prop_type', '')}" for p in picks_list1}
        set2 = {f"{getattr(p, 'player_name', '')}_{getattr(p, 'prop_type', '')}" for p in picks_list2}
        
        intersection = len(set1.intersection(set2))
        return intersection / max(len(set1), 1)
