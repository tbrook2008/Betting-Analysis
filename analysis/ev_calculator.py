"""
analysis/ev_calculator.py — Expected Value calculations for PrizePicks entries.
"""
from typing import List, Dict, Any
import math
from scipy.special import comb

class EVCalculator:
    """Calculates EV for PrizePicks entries, adapting probabilities via correlation."""
    
    PAYOUTS = {
        'power_2': 3.0,
        'power_3': 5.0,
        'power_4': 10.0,
        'power_5': 5.5,  # Arena Floor
        'power_6': 40.0, # Arena Floor
        'flex_3': 2.25,
        'flex_4': 5.0,   
        'flex_5': 10.0,  
        'flex_6': 25.0
    }

    def __init__(self, correlation_engine):
        self.corr_engine = correlation_engine

    def calculate_power_play_ev(self, picks: List[Any], entry_amount: float = 10.0) -> Dict[str, Any]:
        """Calculates EV for an all-or-nothing Power Play."""
        n = len(picks)
        if n < 2 or f'power_{n}' not in self.PAYOUTS:
            return {'ev': -entry_amount, 'roi': -100, 'win_prob': 0.0, 'correlation_score': 0}
            
        payout_multiplier = self.PAYOUTS[f'power_{n}']
        
        # Base probability (product of individual probabilities)
        probs = [min(0.99, max(0.01, getattr(p, 'confidence', 50) / 100.0)) for p in picks]
        independent_prob = math.prod(probs)
        
        # Apply Correlation adjustments
        correlation = self.corr_engine.calculate_combination_correlation(picks)
        adjusted_prob = self.corr_engine.adjust_probability_for_correlation(independent_prob, correlation)
        
        win_amount = entry_amount * payout_multiplier
        ev = (adjusted_prob * win_amount) - ((1 - adjusted_prob) * entry_amount)
        roi = (ev / entry_amount) * 100 if entry_amount > 0 else 0
        
        return {
            'ev': round(ev, 2),
            'roi': round(roi, 1),
            'win_probability': adjusted_prob,
            'correlation_score': correlation
        }

    # Real PrizePicks Arena Minimum Guarantee partial payout structure.
    # Keys = number of legs. Values = dict of {num_hits: payout_multiplier}
    FLEX_PARTIAL_PAYOUTS: dict = {
        3: {3: 2.25, 2: 1.25, 1: 0.0, 0: 0.0}, # Arena usually matches standard here
        4: {4: 5.0,  3: 1.5,  2: 0.4, 1: 0.0, 0: 0.0},
        5: {5: 4.0,  4: 0.5,  3: 0.25, 2: 0.0, 1: 0.0, 0: 0.0}, # Arena Floor
        6: {6: 27.0, 5: 2.0,  4: 0.4, 3: 0.0, 2: 0.0, 1: 0.0, 0: 0.0}, # Arena Floor
    }

    def calculate_flex_play_ev(self, picks: List[Any], entry_amount: float = 10.0) -> Dict[str, Any]:
        """Calculates EV for a Flex Play using exact per-outcome partial payouts."""
        n = len(picks)
        if n < 3 or n not in self.FLEX_PARTIAL_PAYOUTS:
            return {'ev': -entry_amount, 'roi': -100, 'win_probability': 0.0, 'correlation_score': 0}

        probs = [min(0.99, max(0.01, getattr(p, 'confidence', 50) / 100.0)) for p in picks]
        avg_prob = sum(probs) / n

        correlation = self.corr_engine.calculate_combination_correlation(picks)
        # Apply correlation adjustment to the per-leg baseline
        adj_prob = float(min(0.99, max(0.01, avg_prob * (1 + correlation * 0.3))))

        payout_map = self.FLEX_PARTIAL_PAYOUTS[n]

        # Calculate EV summed across ALL outcomes (exact binomial)
        ev = 0.0
        total_win_prob = 0.0  # probability of getting any payout back
        for k in range(n + 1):
            p_exactly_k = float(comb(n, k, exact=False)) * (adj_prob ** k) * ((1 - adj_prob) ** (n - k))
            payout_mult = payout_map.get(k, 0.0)
            if payout_mult > 0:
                total_win_prob += p_exactly_k
            # EV contribution: (prob of k hits) * (payout - stake if win, or -stake if loss)
            if payout_mult >= 1.0:
                ev += p_exactly_k * (entry_amount * payout_mult - entry_amount)
            else:
                # Partial return less than stake (e.g. 0.4x) still a net loss
                ev += p_exactly_k * (entry_amount * payout_mult - entry_amount)

        roi = (ev / entry_amount) * 100

        return {
            'ev': round(ev, 2),
            'roi': round(roi, 1),
            'win_probability': round(total_win_prob, 4),
            'correlation_score': correlation
        }

        
    def is_positive_ev(self, ev_data: dict, min_roi_threshold: float = 5.0) -> bool:
        """Determines if the EV metric dict meets positive criteria."""
        return ev_data.get('ev', 0) > 0 and ev_data.get('roi', 0) >= min_roi_threshold
