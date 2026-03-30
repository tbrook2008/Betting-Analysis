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
        'power_5': 20.0,
        'power_6': 25.0,
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

    def calculate_flex_play_ev(self, picks: List[Any], entry_amount: float = 10.0) -> Dict[str, Any]:
        """Calculates EV for a Flex Play using Binomial Probability approximations."""
        n = len(picks)
        if n < 3 or f'flex_{n}' not in self.PAYOUTS:
            return {'ev': -entry_amount, 'roi': -100, 'win_prob': 0.0, 'correlation_score': 0}
            
        k = n - 1 # PrizePicks typically pays profit on N or N-1 hits.
        
        probs = [min(0.99, getattr(p, 'confidence', 50) / 100.0) for p in picks]
        avg_prob = sum(probs) / n
        
        # Binomial distribution for hitting k or more
        flex_prob = sum(
            comb(n, i) * (avg_prob ** i) * ((1 - avg_prob) ** (n - i))
            for i in range(k, n + 1)
        )
        
        correlation = self.corr_engine.calculate_combination_correlation(picks)
        adjusted_prob = self.corr_engine.adjust_probability_for_correlation(flex_prob, correlation)
        
        payout_multiplier = self.PAYOUTS[f'flex_{n}']
        ev = (adjusted_prob * (entry_amount * payout_multiplier)) - ((1 - adjusted_prob) * entry_amount)
        roi = (ev / entry_amount) * 100
        
        return {
            'ev': round(ev, 2),
            'roi': round(roi, 1),
            'win_probability': adjusted_prob,
            'correlation_score': correlation
        }
        
    def is_positive_ev(self, ev_data: dict, min_roi_threshold: float = 5.0) -> bool:
        """Determines if the EV metric dict meets positive criteria."""
        return ev_data.get('ev', 0) > 0 and ev_data.get('roi', 0) >= min_roi_threshold
