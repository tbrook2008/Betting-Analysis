"""
analysis/correlation_engine.py — Identifies and quantifies relationships between props.
"""
from typing import List, Dict, Any, Tuple

class CorrelationEngine:
    """
    Analyzes correlations between MLB props to adjust combined win probabilities.
    """
    
    def __init__(self):
        self.correlation_rules = {
            'same_team_hitters_same_game': {
                'type': 'positive',
                'strength': 0.25,
                'description': 'Hitters from same team benefit from game script'
            },
            'pitcher_strikeouts_vs_team_hits': {
                'type': 'negative',
                'strength': -0.35,
                'description': 'Pitcher doing well means fewer hits for opposing team'
            },
            'hitter_hr_and_game_total_over': {
                'type': 'positive',
                'strength': 0.30,
                'description': 'Home runs drive game totals'
            },
            'same_game_both_pitchers_high_k': {
                'type': 'negative',
                'strength': -0.20,
                'description': 'Both pitchers dominating is unlikely'
            },
            'hitter_hits_and_team_runs_over': {
                'type': 'positive',
                'strength': 0.28,
                'description': 'Hits lead to runs for team'
            },
            'opposing_team_hitters': {
                'type': 'neutral',
                'strength': 0.0,
                'description': 'Different teams, no correlation'
            }
        }

    def identify_correlation_type(self, pick1: Any, pick2: Any) -> Tuple[str, float, str]:
        """Match two picks against correlation rules."""
        p1_type, p2_type = getattr(pick1, 'prop_type', '').lower(), getattr(pick2, 'prop_type', '').lower()
        p1_team, p2_team = getattr(pick1, 'team', ''), getattr(pick2, 'team', '')
        
        # Rule 1: Same team hitters
        if p1_team and p2_team and p1_team == p2_team and p1_type in ("hits", "total bases", "home runs", "singles", "runs", "rbis") and p2_type in ("hits", "total bases", "home runs", "singles", "runs", "rbis"):
            c = self.correlation_rules['same_team_hitters_same_game']
            return c['type'], c['strength'], c['description']
            
        # Default neutral
        c = self.correlation_rules['opposing_team_hitters']
        return c['type'], c['strength'], c['description']

    def calculate_combination_correlation(self, picks_list: List[Any]) -> float:
        """Calculate average pairwise correlation for a combination of picks."""
        if len(picks_list) < 2:
            return 0.0
            
        total_strength = 0.0
        pairs = 0
        for i in range(len(picks_list)):
            for j in range(i + 1, len(picks_list)):
                _, strength, _ = self.identify_correlation_type(picks_list[i], picks_list[j])
                total_strength += strength
                pairs += 1
                
        return total_strength / pairs if pairs > 0 else 0.0

    def adjust_probability_for_correlation(self, independent_prob: float, correlation_score: float) -> float:
        """Adjust independent prob based on correlation strength."""
        if correlation_score > 0:
            adjusted_prob = independent_prob * (1 + (correlation_score * 0.5))
        elif correlation_score < 0:
            adjusted_prob = independent_prob * (1 + (correlation_score * 0.3))
        else:
            adjusted_prob = independent_prob

        # Cap it
        return min(max(adjusted_prob, 0.0), 0.999)

    def get_correlation_warnings(self, picks_list: List[Any]) -> List[str]:
        """Identify strong negative correlations (< -0.3)."""
        warnings = []
        for i in range(len(picks_list)):
            for j in range(i + 1, len(picks_list)):
                c_type, strn, desc = self.identify_correlation_type(picks_list[i], picks_list[j])
                if strn <= -0.3:
                    warnings.append(f"Negative EV Pair: {getattr(picks_list[i], 'player_name', 'Unknown')} and {getattr(picks_list[j], 'player_name', 'Unknown')} - {desc}")
        return warnings
