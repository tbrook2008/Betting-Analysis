import math
import random
import numpy as np

def calculate_kelly_goblin(hit_rate=0.72):
    """
    Calculate EV and Optimal Kelly Fraction for a 6-leg Flex on PrizePicks 
    with Goblin payouts: 4x (6/6), 1.25x (5/6), 0.4x (4/6).
    """
    p6 = hit_rate ** 6
    p5 = 6 * (hit_rate ** 5) * (1 - hit_rate)
    p4 = 15 * (hit_rate ** 4) * ((1 - hit_rate) ** 2)
    p_loss = 1 - (p6 + p5 + p4)
    
    ev_per_dollar = (p6 * 4.0) + (p5 * 1.25) + (p4 * 0.4) - 1.0
    
    def expected_log(f):
        if f <= 0 or f >= 1:
            return -float('inf')
        try:
            return (
                p6 * math.log(1 + f * 3.0) +
                p5 * math.log(1 + f * 0.25) +
                p4 * math.log(1 + f * -0.6) +
                p_loss * math.log(1 - f)
            )
        except ValueError:
            return -float('inf')

    # Find Kelly via grid search
    best_f = 0.0
    best_log = -float('inf')
    for i in range(1, 1000):
        f = i / 1000.0
        e = expected_log(f)
        if e > best_log:
            best_log = e
            best_f = f
            
    return ev_per_dollar, best_f, (p6, p5, p4, p_loss)

def simulate_bankroll():
    bankroll = 22.0
    min_bet = 3.0
    hit_rate = 0.72
    iterations = 10000
    bets_per_sim = 500
    
    ev_per_dollar, best_f, probs = calculate_kelly_goblin(hit_rate)
    p6, p5, p4, p_loss = probs
    
    print(f"--- 6-Leg Flex Goblin Simulation (Hit Rate: {hit_rate*100}%) ---")
    print(f"Prob 6/6: {p6:.4f} (Payout: 4x)")
    print(f"Prob 5/6: {p5:.4f} (Payout: 1.25x)")
    print(f"Prob 4/6: {p4:.4f} (Payout: 0.4x)")
    print(f"Expected Value (EV): {ev_per_dollar*100:+.2f}%")
    print(f"Optimal Kelly Fraction: {best_f*100:.2f}%")
    
    # Risk of Ruin using Optimal Kelly but constrained by $3 minimum
    ruined_count = 0
    success_count = 0
    goal = 100.0
    
    for _ in range(iterations):
        current_br = bankroll
        for _ in range(bets_per_sim):
            if current_br < min_bet:
                ruined_count += 1
                break
            if current_br >= goal:
                success_count += 1
                break
                
            bet_size = current_br * best_f
            # Cap by minimum bet logic
            if bet_size < min_bet:
                bet_size = min_bet
                
            rand_val = random.random()
            if rand_val < p6:
                profit = bet_size * 3.0
            elif rand_val < p6 + p5:
                profit = bet_size * 0.25
            elif rand_val < p6 + p5 + p4:
                profit = bet_size * -0.6
            else:
                profit = -bet_size
                
            current_br += profit
            
    print(f"Risk of Ruin ($22 to <$3): {(ruined_count / iterations) * 100:.2f}%")
    print(f"Success Rate (Reached $100): {(success_count / iterations) * 100:.2f}%")

if __name__ == '__main__':
    simulate_bankroll()
