"""
picks/stack_builder.py — Builds correlated same-game prop stacks.
"""
from typing import List, Dict, Any
import itertools

class StackBuilder:
    """Builds highly correlated same-game/same-team pick combinations."""
    
    def __init__(self, correlation_engine, ev_calculator):
        self.corr_engine = correlation_engine
        self.ev_calc = ev_calculator
        
    def find_stackable_games(self, date_str: str, picks_list: List[Any]) -> List[Dict[str, Any]]:
        """Groups picks by game and scores the game's viability for a stack."""
        games = {}
        for pick in picks_list:
            if getattr(pick, 'confidence', 0) < 60:
                continue
            gid = getattr(pick, 'game_id', 'unknown')
            if gid not in games:
                games[gid] = {'picks': [], 'score': 0.0}
            games[gid]['picks'].append(pick)
            
        stackable = []
        for gid, data in games.items():
            if len(data['picks']) >= 2:
                # Basic mock score based on pick count
                data['score'] = len(data['picks']) * 1.5
                stackable.append({'game_id': gid, 'score': data['score'], 'picks': data['picks']})
                
        stackable.sort(key=lambda x: x['score'], reverse=True)
        return stackable
        
    def build_same_team_stack(self, game_dict: Dict[str, Any], target_size: int = 3) -> List[Dict[str, Any]]:
        """Builds combinations of picks from the same team."""
        picks = game_dict['picks']
        
        teams = {}
        for p in picks:
            t = getattr(p, 'team', 'unknown')
            if t not in teams: teams[t] = []
            teams[t].append(p)
            
        stacks = []
        for team, team_picks in teams.items():
            if len(team_picks) < target_size:
                continue
            
            for combo in itertools.combinations(team_picks, target_size):
                combo_list = list(combo)
                corr = self.corr_engine.calculate_combination_correlation(combo_list)
                ev_data = self.ev_calc.calculate_power_play_ev(combo_list)
                
                if ev_data['ev'] > 0 and corr > 0.15:
                    stacks.append({
                        'picks': combo_list,
                        'correlation_score': corr,
                        'ev': ev_data['ev'],
                        'win_probability': ev_data['win_probability'],
                        'narrative': self.get_stack_narrative(combo_list)
                    })
                    
        stacks.sort(key=lambda x: x['ev'], reverse=True)
        return stacks
        
    def build_mixed_stack(self, game_dict: Dict[str, Any], target_size: int = 3) -> List[Dict[str, Any]]:
        """Builds game-level stacks using opposing teams safely."""
        # Simplified: Just find highest EV combinations that don't invoke negative correlations
        picks = game_dict['picks']
        if len(picks) < target_size:
            return []
            
        stacks = []
        for combo in itertools.combinations(picks, target_size):
            combo_list = list(combo)
            corr = self.corr_engine.calculate_combination_correlation(combo_list)
            
            # Avoid negative correlations in mixed stacks
            if corr < -0.1:
                continue
                
            ev_data = self.ev_calc.calculate_flex_play_ev(combo_list) # Flex is safer for mixed
            
            if ev_data['ev'] > 0:
                stacks.append({
                    'picks': combo_list,
                    'correlation_score': corr,
                    'ev': ev_data['ev'],
                    'win_probability': ev_data['win_probability'],
                    'narrative': 'Mixed game stack optimized for positive conditions.'
                })
        return stacks
        
    def get_stack_narrative(self, stack: List[Any]) -> str:
        names = [getattr(p, 'player_name', '') for p in stack]
        return f"Positive correlation stack on {', '.join(names)} relying on strong team offensive production."
