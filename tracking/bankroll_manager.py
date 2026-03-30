"""
tracking/bankroll_manager.py — Manage Kelly Criterion sizing and risk thresholds.
"""
from datetime import datetime
from typing import Dict, Any, List

class BankrollManager:
    """Manages bankroll, unit sizing, and risk controls."""
    
    def __init__(self, starting_bankroll: float, risk_tolerance: str = 'conservative'):
        self.starting_bankroll = starting_bankroll
        self.current_bankroll = starting_bankroll
        self.risk_tolerance = risk_tolerance
        self.bet_history = []
        
        self.kelly_fractions = {
            'conservative': 0.25,  # Quarter Kelly
            'moderate': 0.50,      # Half Kelly
            'aggressive': 1.0      # Full Kelly
        }
        
    def calculate_kelly_size(self, win_prob: float, payout_multiplier: float, current_bankroll: float) -> float:
        """Fraction of bankroll to bet based on Kelly Criterion."""
        b = payout_multiplier - 1
        p = win_prob
        q = 1 - p
        
        if b <= 0: return 0.0
        
        kelly_fraction = (b * p - q) / b
        adjusted_fraction = kelly_fraction * self.kelly_fractions.get(self.risk_tolerance, 0.25)
        
        final_fraction = min(adjusted_fraction, 0.15) # Max 15% per entry
        
        if final_fraction > 0:
            final_fraction = max(final_fraction, 0.02) # Min 2% on positive EV
            
        return current_bankroll * final_fraction

    def get_recommended_entry_size(self, entry: Dict[str, Any], current_bankroll: float) -> float:
        win_prob = entry.get('win_probability', 0)
        payout = entry.get('payout_multiplier', 0)
        
        kelly_size = self.calculate_kelly_size(win_prob, payout, current_bankroll)
        recommended_size = max(round(kelly_size), 3.0) # PrizePicks Minimum is $3
        
        return float(recommended_size)

    def check_risk_limits(self, portfolio: List[Dict[str, Any]], current_bankroll: float) -> List[Dict[str, Any]]:
        total_risk = sum(entry.get('entry_amount', 0) for entry in portfolio)
        risk_percentage = (total_risk / current_bankroll) * 100 if current_bankroll > 0 else 100
        
        risk_limits = {
            'conservative': 20, 
            'moderate': 35,
            'aggressive': 50
        }
        max_risk = risk_limits.get(self.risk_tolerance, 20)
        
        if risk_percentage > max_risk:
            scale_factor = max_risk / risk_percentage
            for entry in portfolio:
                sz = entry.get('entry_amount', 3) * scale_factor
                entry['entry_amount'] = max(round(sz), 3)
                
        return portfolio

    def check_stop_loss(self, current_bankroll: float, starting_bankroll: float) -> Dict[str, Any]:
        if starting_bankroll <= 0: return {'stop_trading': False}
            
        drawdown_pct = ((starting_bankroll - current_bankroll) / starting_bankroll) * 100
        stop_loss_thresholds = {
            'conservative': 30,  
            'moderate': 40,
            'aggressive': 50
        }
        
        threshold = stop_loss_thresholds.get(self.risk_tolerance, 30)
        
        if drawdown_pct >= threshold:
            return {
                'stop_trading': True,
                'reason': f'Hit {drawdown_pct:.1f}% drawdown (limit: {threshold}%)',
                'recommendation': 'Reassess model performance before continuing'
            }
            
        return {'stop_trading': False}

    def update_bankroll(self, entry_result: str, entry_size: float, payout_multiplier: float) -> float:
        if entry_result == 'win':
            profit = entry_size * (payout_multiplier - 1)
            self.current_bankroll += profit
        else:
            profit = -entry_size
            self.current_bankroll -= entry_size
            
        self.bet_history.append({
            'date': datetime.now(),
            'size': entry_size,
            'result': entry_result,
            'profit_loss': profit,
            'bankroll_after': self.current_bankroll
        })
        return self.current_bankroll
