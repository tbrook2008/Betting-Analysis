"""
analysis/game_simulator.py
Game-Script Simulation for Plate Appearances
"""

import random

def simulate_plate_appearances(player_name: str, team_name: str, venue: str, park_factor: float) -> float:
    """
    Runs a Monte Carlo simulation (1000 iterations) of a baseball game to predict expected 
    Plate Appearances (PA) for a batter.
    Standard base PA is 4.0. Returns a multiplier (expected PA / 4.0).
    """
    iterations = 1000
    total_pas = 0.0
    
    # Fallback for park factor if not available
    pf = park_factor if park_factor is not None else 1.0

    for _ in range(iterations):
        # Mean runs based on average (4.5) * park_factor
        mean_runs = 4.5 * pf
        # Simulated runs (cannot be negative)
        sim_runs = max(0.0, random.gauss(mean_runs, 2.5))
        # Left on base is typically around 7 on average per 9 innings
        lob = max(0.0, random.gauss(7.0, 2.0))
        # Team Plate Appearances = 27 outs + runs + left on base
        team_pas = 27.0 + sim_runs + lob
        
        # Player gets approximately 1/9th of the team's total Plate Appearances
        player_pas = team_pas / 9.0
        total_pas += player_pas
        
    expected_pa = total_pas / iterations
    
    return expected_pa / 4.0
