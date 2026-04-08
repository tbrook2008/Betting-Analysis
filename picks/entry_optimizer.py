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
        
        # v4.0 Filter: Specific handling for high-variance Home Runs
        # Standard picks use min_confidence (default 60)
        # Home Runs require "Very High Confidence" (70%+) per user request
        filtered_picks = []
        for p in picks_list:
            conf = getattr(p, 'confidence', 0)
            p_type = getattr(p, 'prop_type', '').lower()
            
            if 'home run' in p_type:
                if conf >= 70:
                    filtered_picks.append(p)
            elif conf >= min_confidence:
                filtered_picks.append(p)
        
        # Sort by confidence and take top 15 to cap combinations
        filtered_picks = sorted(filtered_picks, key=lambda x: getattr(x, 'confidence', 0), reverse=True)[:15]

        # Fix 6: Market implied-probability filter
        def _has_model_edge(pick) -> bool:
            implied_prob = getattr(pick, 'market_implied_prob', None)
            if implied_prob is None:
                return True
            model_prob = getattr(pick, 'confidence', 50) / 100.0
            return (model_prob - implied_prob) >= 0.05
        
        filtered_picks = [p for p in filtered_picks if _has_model_edge(p)]
                                
        entries = []
        # PrizePicks supports 2-6 picks per entry
        for size in range(2, 7):
            for combo in itertools.combinations(filtered_picks, size):
                combo_list = list(combo)
                
                # 2. Strict Filter: Prevent the same player from appearing multiple times in a single entry
                players_in_combo = {getattr(p, 'player_name', '') for p in combo_list}
                if len(players_in_combo) < size:
                    continue
                    
                # 3. PrizePicks Rule: Entries MUST contain players from at least 2 different teams
                teams_in_combo = {getattr(p, 'team', '') for p in combo_list if getattr(p, 'team', '')}
                if len(teams_in_combo) < 2 and len(teams_in_combo) > 0:
                    continue
                
                # ── [v5.1 Fix 3] Quality Gate for 6-leg entries ────────────────
                # Require at least 5 of 6 legs to be ≥85% confidence.
                # This prevents weak-leg breakdowns (e.g., Apr 6 Yordan Alvarez Runs).
                if size == 6:
                    high_conf_count = sum(1 for p in combo_list if getattr(p, 'confidence', 0) >= 85)
                    if high_conf_count < 5:
                        continue
                
                # Check negative correlation warnings before calc
                if self.comb_analyzer.has_strong_negative_correlation(combo_list):
                    continue
                
                power_ev = self.ev_calc.calculate_power_play_ev(combo_list)
                flex_ev = None
                
                if size >= 3:
                    flex_ev = self.ev_calc.calculate_flex_play_ev(combo_list)
                
                is_power_ev_positive = self.ev_calc.is_positive_ev(power_ev)
                is_flex_ev_positive = flex_ev and self.ev_calc.is_positive_ev(flex_ev)
                
                # v4.0 Safety: Force Flex-only for Home Run props due to variance
                # (User emphasized "very high confidence" and lower tolerance for risk)
                has_hr = any('home run' in getattr(p, 'prop_type', '').lower() for p in combo_list)
                if has_hr:
                    is_power_ev_positive = False  # Never allow Power plays for HR entries
                
                # ── [v5.1 Fix 1] Force Flex for all 5-6 leg entries ───────────
                # Data shows Flex-6 accounts for 95% of all profits.
                # Power plays for large entries are statistically unprofitable.
                if size >= 5:
                    is_power_ev_positive = False

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
        """
        Select a diverse set of entries.
        v5.1: Flex-6 entries get absolute priority. Smaller Power entries are
        only added if budget remains AND they use non-overlapping picks.
        """
        risk_params = {
            'conservative': {'max_per_entry': 0.15, 'max_daily_risk': 0.20, 'prefer_flex': True},
            'moderate':      {'max_per_entry': 0.15, 'max_daily_risk': 0.35, 'prefer_flex': True},
            'aggressive':    {'max_per_entry': 0.20, 'max_daily_risk': 0.50, 'prefer_flex': False}
        }
        
        params = risk_params.get(risk_tolerance, risk_params['conservative'])
        daily_budget = bankroll * params['max_daily_risk']
        
        # ── [v5.1 Fix 1] Separate Flex-6 from all other entries ───────────────
        flex6_entries = [e for e in entries_list if e['entry_type'] == 'flex_6']
        flex5_entries = [e for e in entries_list if e['entry_type'] == 'flex_5']
        other_entries = [e for e in entries_list if e['entry_type'] not in ('flex_6', 'flex_5')]

        # ── [v5.1 Fix 2] Conditional Kelly sizing per entry type ──────────────
        # Flex-6 gets the biggest slice since it drives 95% of profits.
        type_budget_caps = {
            'flex_6': min(bankroll * 0.20, daily_budget * 0.70),  # Up to 70% of daily budget
            'flex_5': min(bankroll * 0.15, daily_budget * 0.50),
            'other':  min(bankroll * 0.05, daily_budget * 0.15),  # Hard cap: 5% of bankroll
        }

        selected_entries = []
        used_player_props: set = set()
        budget_remaining = daily_budget

        def _try_add(entry_pool, cap_key):
            nonlocal budget_remaining
            for entry in self.rank_entries(entry_pool, 'ev'):
                pick_sigs = {f"{getattr(p, 'player_name', '')}_{getattr(p, 'prop_type', '')}" for p in entry['picks']}
                if not any(sig in used_player_props for sig in pick_sigs):
                    alloc = type_budget_caps[cap_key]
                    if budget_remaining >= alloc and alloc >= 3.0:
                        entry['entry_amount'] = alloc
                        selected_entries.append(entry)
                        used_player_props.update(pick_sigs)
                        budget_remaining -= alloc
                        return  # Only one primary entry per type

        # Priority 1: Best Flex-6
        _try_add(flex6_entries, 'flex_6')
        # Priority 2: Best Flex-5 (non-overlapping)
        _try_add(flex5_entries, 'flex_5')
        # Priority 3: Best remaining (Power-2/3 only if budget left)
        if not params['prefer_flex']:
            _try_add(other_entries, 'other')
                    
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
