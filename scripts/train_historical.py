#!/usr/bin/env python3
"""
scripts/train_historical.py - Batch generate and auto-grade historical picks to train the Teacher model.
"""
import click
import pandas as pd
from rich.console import Console

import sys
import os

# Add parent directory to path so we can import project modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.demo_mode import DemoMode
from tracking.performance_tracker import PerformanceTracker
from tracking.results_grader import ResultsGrader
from analysis.teacher import Teacher

console = Console()

@click.command()
@click.option('--start-date', required=True, help='Start date (YYYY-MM-DD)')
@click.option('--end-date', required=True, help='End date (YYYY-MM-DD)')
def train(start_date, end_date):
    """Run historical backtest simulation and auto-grade to train the AI model."""
    dates = pd.date_range(start=start_date, end=end_date)
    tracker = PerformanceTracker()
    demo_mode = DemoMode(tracker)
    grader = ResultsGrader(tracker)
    teacher = Teacher()
    
    console.print(f"[bold cyan]🚀 Starting Historical Training: {start_date} to {end_date}[/]")
    console.print("[dim]Note: Gemini API is bypassed during demo mode.[/]\n")
    
    total_graded = 0
    
    for d in dates:
        date_str = d.strftime('%Y-%m-%d')
        console.print(f"--- [bold]Processing {date_str}[/] ---")
        
        with console.status(f"[{date_str}] Generating demo picks (bypassing AI vetter)..."):
            # Generates picks based on historical data up to `date_str`
            try:
                portfolio = demo_mode.run_demo_picks(date_str)
                console.print(f"  [green]Generated {len(portfolio)} demo entries.[/]")
            except Exception as e:
                console.print(f"  [red]Failed to generate picks for {date_str}: {e}[/]")
                continue
                
        if not portfolio:
            console.print("  [yellow]No qualifying entries generated.[/]")
            continue
            
        with console.status(f"[{date_str}] Fetching actual box scores and grading..."):
            try:
                # Fetches actual results and calls teacher.run_daily_retro(date)
                graded_count = grader.grade_date(date_str, is_demo=True)
                console.print(f"  [bold green]✅ Graded {graded_count} entries. Teacher model updated.[/]")
                total_graded += graded_count
            except Exception as e:
                console.print(f"  [red]Failed to grade {date_str}: {e}[/]")
                
    console.print(f"\n[bold magenta]🎉 Training Complete![/] Graded a total of {total_graded} historical entries.")
    
if __name__ == '__main__':
    train()
