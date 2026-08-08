#!/usr/bin/env python3
"""
scripts/optimize_hyperparameters.py - Autonomous Optuna-based Hyperparameter Optimizer
Runs fast, in-memory simulations across historical dates to find the exact optimal configuration for ROI.
"""
import click
import pandas as pd
import optuna
from rich.console import Console
import sys
import os
import logging

# Suppress overly verbose logging during optimization
optuna.logging.set_verbosity(optuna.logging.WARNING)
logging.getLogger("uvicorn").setLevel(logging.CRITICAL)

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from utils.demo_mode import DemoMode
from tracking.performance_tracker import PerformanceTracker
from tracking.results_grader import ResultsGrader

console = Console()

def objective(trial, start_date, end_date):
    # 1. Suggest parameters for this trial
    min_conf = trial.suggest_int("min_confidence", 52, 65)
    hits_r7 = trial.suggest_float("hits_r7", 0.05, 0.40)
    hits_r14 = trial.suggest_float("hits_r14", 0.05, 0.40)
    
    # Normalize weights so they sum to a reasonable baseline
    base_sum = 0.20 + 0.15 # Original r7 and r14
    new_sum = hits_r7 + hits_r14
    factor = base_sum / new_sum if new_sum > 0 else 1.0
    
    hits_r7 *= factor
    hits_r14 *= factor
    
    kelly_fraction = trial.suggest_float("kelly_fraction", 0.10, 0.35)
    max_corr_neg = trial.suggest_float("max_correlation_negative", -0.40, -0.15)
    
    # 2. Apply Overrides globally
    overrides = {
        'MIN_CONFIDENCE': min_conf,
        'HITS_WEIGHTS': {
            'rolling_avg_7': hits_r7,
            'rolling_avg_14': hits_r14
        },
        'BANKROLL_CONFIG': {
            'kelly_fraction': kelly_fraction
        },
        'PRIZEPICKS_CONFIG': {
            'max_correlation_negative': max_corr_neg
        }
    }
    config.apply_overrides(overrides)
    
    # 3. Setup in-memory tracking
    tracker = PerformanceTracker(in_memory=True)
    demo_mode = DemoMode(tracker)
    grader = ResultsGrader(tracker)
    
    dates = pd.date_range(start=start_date, end=end_date)
    
    # 4. Run backtest simulation
    for d in dates:
        date_str = d.strftime('%Y-%m-%d')
        try:
            # Generate demo entries using the tweaked config
            portfolio = demo_mode.run_demo_picks(date_str)
            if portfolio:
                # Grade the entries
                grader.grade_date(date_str, is_demo=True)
        except Exception:
            # If a configuration crashes or fails to fetch data, we penalize it
            return -100.0
            
    # 5. Evaluate result
    stats = tracker.calculate_statistics()
    # Optimize for total profit/ROI (Return ROI)
    # If no entries were placed, ROI is 0, which is worse than positive ROI but better than negative
    roi = stats.get('roi', 0.0)
    
    # Optional: We could penalize configurations that don't place enough bets
    # if stats.get('total_entries', 0) < len(dates):
    #     roi -= 5.0
        
    return roi

@click.command()
@click.option('--trials', default=5, type=int, help='Number of optuna trials to run')
@click.option('--start-date', default='2026-08-01', help='Start date for simulation window')
@click.option('--end-date', default='2026-08-07', help='End date for simulation window')
def optimize(trials, start_date, end_date):
    """Run Optuna hyperparameter optimization."""
    console.print(f"\n[bold cyan]🧪 Starting Bayesian Hyperparameter Optimization[/]")
    console.print(f"Running {trials} trials over historical dates: {start_date} to {end_date}...")
    console.print("[dim]Using in-memory SQLite database to preserve real data.[/]\n")
    
    study = optuna.create_study(direction="maximize")
    
    with console.status(f"Optimizing... this may take a few minutes."):
        study.optimize(lambda trial: objective(trial, start_date, end_date), n_trials=trials)
        
    console.print(f"\n[bold green]✅ Optimization Complete![/]")
    console.print(f"Best ROI achieved: [bold]{study.best_value:+.2f}%[/]")
    console.print("\n[bold]Best Parameters Found:[/]")
    for key, value in study.best_params.items():
        console.print(f"  {key}: {value:.4f}" if isinstance(value, float) else f"  {key}: {value}")
        
    console.print("\n[dim]To apply these, manually update config.py with the values above.[/]")

if __name__ == '__main__':
    optimize()
