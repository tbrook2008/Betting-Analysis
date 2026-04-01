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
        p1_type = getattr(pick1, 'prop_type', '').lower()
        p2_type = getattr(pick2, 'prop_type', '').lower()
        p1_team = getattr(pick1, 'team', '')
        p2_team = getattr(pick2, 'team', '')
        p1_opponent = getattr(pick1, 'opponent', '')
        p2_opponent = getattr(pick2, 'opponent', '')

        _BATTER_TYPES = {"hits", "total bases", "home runs", "singles", "runs", "rbis"}
        _PITCHER_TYPES = {"pitcher strikeouts", "strikeouts"}

        p1_is_batter = any(t in p1_type for t in _BATTER_TYPES)
        p2_is_batter = any(t in p2_type for t in _BATTER_TYPES)
        p1_is_pitcher = any(t in p1_type for t in _PITCHER_TYPES)
        p2_is_pitcher = any(t in p2_type for t in _PITCHER_TYPES)

        # Rule 1: Same team hitters — positive correlation (game script benefit)
        if p1_team and p2_team and p1_team == p2_team and p1_is_batter and p2_is_batter:
            c = self.correlation_rules['same_team_hitters_same_game']
            return c['type'], c['strength'], c['description']

        # Rule 2: Pitcher Ks vs opposing team batter Hits — negative correlation
        # If a pitcher is facing opposing batters in the same game, Ks hurt hits
        if p1_is_pitcher and p2_is_batter:
            if p1_opponent and p2_team and p1_opponent.lower() == p2_team.lower():
                c = self.correlation_rules['pitcher_strikeouts_vs_team_hits']
                return c['type'], c['strength'], c['description']
        if p2_is_pitcher and p1_is_batter:
            if p2_opponent and p1_team and p2_opponent.lower() == p1_team.lower():
                c = self.correlation_rules['pitcher_strikeouts_vs_team_hits']
                return c['type'], c['strength'], c['description']

        # Rule 3: Same-game both pitchers high Ks — negative correlation (unlikely both dominate)
        if p1_is_pitcher and p2_is_pitcher:
            same_game = (p1_team and p2_team and p1_opponent and p2_opponent and
                        (p1_team.lower() == p2_opponent.lower() or p2_team.lower() == p1_opponent.lower()))
            if same_game:
                c = self.correlation_rules['same_game_both_pitchers_high_k']
                return c['type'], c['strength'], c['description']

        # Rule 4: Hitter HR and game total Over — positive correlation
        if ('home runs' in p1_type and 'total' in p2_type) or ('home runs' in p2_type and 'total' in p1_type):
            c = self.correlation_rules['hitter_hr_and_game_total_over']
            return c['type'], c['strength'], c['description']

        # Rule 5: Hitter hits and team runs over — positive correlation
        if (p1_is_batter and 'total' in p2_type) or (p2_is_batter and 'total' in p1_type):
            c = self.correlation_rules['hitter_hits_and_team_runs_over']
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
