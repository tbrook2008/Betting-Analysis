"""
picks/entry_optimizer.py — Optimizes entry selection and sizing for PrizePicks.
"""
from typing import List, Dict, Any
import itertools
from picks.combination_analyzer import CombinationAnalyzer

class EntryOptimizer:
    """Optimizes entry selection and sizing for PrizePicks to maximize EV."""
    
    def __init__(self, ev_calculator):
        self.ev_calc = ev_calculator
        self.comb_analyzer = CombinationAnalyzer()

    def generate_all_entries(self, picks_list: List[Any], min_confidence: int = 60) -> List[Dict[str, Any]]:
        """Generate all positive EV entries from given picks."""
        # Sort by confidence and take top 15 to cap combinations at ~5000 max (preventing 7m+ combos)
        filtered_picks = sorted([p for p in picks_list if getattr(p, 'confidence', 0) >= min_confidence], 
                                key=lambda x: getattr(x, 'confidence', 0), reverse=True)[:15]
        entries = []
        # PrizePicks supports 2-6 picks per entry
        for size in range(2, 7):
            for combo in itertools.combinations(filtered_picks, size):
                combo_list = list(combo)
                
                # Check negative correlation warnings before calc
                if self.comb_analyzer.has_strong_negative_correlation(combo_list):
                    continue
                
                power_ev = self.ev_calc.calculate_power_play_ev(combo_list)
                flex_ev = None
                
                if size >= 3:
                    flex_ev = self.ev_calc.calculate_flex_play_ev(combo_list)
                
                is_power_ev_positive = self.ev_calc.is_positive_ev(power_ev)
                is_flex_ev_positive = flex_ev and self.ev_calc.is_positive_ev(flex_ev)
                
                # We only keep positive EV
                if is_power_ev_positive or is_flex_ev_positive:
                    best_mode = 'power'
                    best_ev = power_ev['ev']
                    best_data = power_ev
                    
                    if is_flex_ev_positive and (not is_power_ev_positive or flex_ev['ev'] > power_ev['ev']):
                        best_mode = 'flex'
                        best_ev = flex_ev['ev']
                        best_data = flex_ev
                        
                    entries.append({
                        'picks': combo_list,
                        'num_picks': size,
                        'entry_type': f"{best_mode}_{size}",
                        'recommended_type': best_mode,
                        'ev': best_data['ev'],
                        'roi': best_data['roi'],
                        'win_probability': best_data['win_probability'],
                        'correlation_score': best_data.get('correlation_score', 0),
                        'payout_multiplier': self.ev_calc.PAYOUTS.get(f"{best_mode}_{size}", 0)
                    })
                    
        return entries

    def rank_entries(self, entries_list: List[Dict[str, Any]], strategy: str = 'ev') -> List[Dict[str, Any]]:
        """Rank entries based on 'ev', 'roi', or 'win_rate'."""
        if strategy == 'roi':
            return sorted(entries_list, key=lambda x: x['roi'], reverse=True)
        elif strategy == 'win_rate':
            return sorted(entries_list, key=lambda x: x['win_probability'], reverse=True)
        # default to EV
        return sorted(entries_list, key=lambda x: x['ev'], reverse=True)

    def optimize_portfolio(self, entries_list: List[Dict[str, Any]], bankroll: float, risk_tolerance: str = 'conservative') -> List[Dict[str, Any]]:
        """Select a diverse set of entries minimizing overlap."""
        risk_params = {
            'conservative': {'max_per_entry': 0.05, 'max_daily_risk': 0.20, 'prefer_flex': True},
            'moderate': {'max_per_entry': 0.10, 'max_daily_risk': 0.35, 'prefer_flex': False},
            'aggressive': {'max_per_entry': 0.15, 'max_daily_risk': 0.50, 'prefer_flex': False}
        }
        
        params = risk_params.get(risk_tolerance, risk_params['conservative'])
        max_entry_size = bankroll * params['max_per_entry']
        daily_budget = bankroll * params['max_daily_risk']
        
        selected_entries = []
        used_player_props = set()
        budget_remaining = daily_budget
        
        # Sort by best EV first
        for entry in self.rank_entries(entries_list, 'ev'):
            # Preference filter
            if params['prefer_flex'] and entry['recommended_type'] == 'power':
                # Skip or penalize power plays if strictly conservative
                pass 
                
            # Overlap check
            pick_signatures = {f"{getattr(p, 'player_name', '')}_{getattr(p, 'prop_type', '')}" for p in entry['picks']}
            if not any(sig in used_player_props for sig in pick_signatures):
                if budget_remaining >= max_entry_size:
                    # Assign size temporarily, Kelly will override this later
                    entry['entry_amount'] = max_entry_size 
                    selected_entries.append(entry)
                    used_player_props.update(pick_signatures)
                    budget_remaining -= max_entry_size
                    
        return selected_entries

    def calculate_portfolio_metrics(self, portfolio: List[Dict[str, Any]], bankroll: float) -> Dict[str, Any]:
        """Calculates global EV and Risk for a portfolio."""
        total_ev = sum(entry.get('ev', 0) for entry in portfolio)
        total_risk = sum(entry.get('entry_amount', 0) for entry in portfolio)
        portfolio_roi = (total_ev / total_risk) * 100 if total_risk > 0 else 0
        
        return {
            'total_ev': round(total_ev, 2),
            'total_risk': round(total_risk, 2),
            'portfolio_roi': round(portfolio_roi, 1),
            'risk_of_ruin': (total_risk / bankroll) * 100 if bankroll > 0 else 0
        }
