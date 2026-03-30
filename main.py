"""
main.py — CLI entry point for the MLB Betting Analysis system.
Updated to use Click for PrizePicks Optimization.
"""
from __future__ import annotations

import click
import datetime
import json
import sys
from pathlib import Path

from rich.console import Console

console = Console()

@click.group()
def cli():
    """PrizePicks Betting Analysis CLI"""
    pass

@cli.command()
@click.option('--date', default="today", help='Date (YYYY-MM-DD)')
@click.option('--min-confidence', default=60, help='Minimum confidence')
@click.option('--bankroll', default=150.0, help='Current bankroll')
@click.option('--risk', default='conservative', help='Risk tolerance')
@click.option('--source', default=None, help='prizepicks | draftkings | all')
def run(date, min_confidence, bankroll, risk, source):
    """Generate optimized PrizePicks entries"""
    from picks.pick_generator import generate_daily_picks
    from analysis.correlation_engine import CorrelationEngine
    from analysis.ev_calculator import EVCalculator
    from picks.entry_optimizer import EntryOptimizer
    from tracking.bankroll_manager import BankrollManager
    from tracking.performance_tracker import PerformanceTracker
    
    # 🔍 Autonomous Learning Loop
    from analysis.teacher import Teacher
    teacher = Teacher()
    if date == "today" and teacher.is_first_run_today():
        console.print("[bold yellow]🧠 First run today! AI is teaching itself from yesterday's results...[/]")
        teacher.run_daily_retro()

    actual_date = None
    if date.lower() != "today":
        actual_date = datetime.date.fromisoformat(date)
    else:
        actual_date = datetime.date.today()

    console.print(f"\n[bold cyan]🎯 PrizePicks EV Optimization[/] — {actual_date}\n")

    with console.status("Fetching lines and running base models…"):
        picks = generate_daily_picks(
            date=actual_date,
            min_confidence=min_confidence,
            sources=__parse_sources(source),
        )

    if not picks:
        console.print("[yellow]⚠ No qualifying picks today.[/]")
        return
        
    with console.status("Optimizing Entries and calculating correlations…"):
        corr_engine = CorrelationEngine()
        ev_calc = EVCalculator(corr_engine)
        optimizer = EntryOptimizer(ev_calc)
        
        # Generator step
        entries = optimizer.generate_all_entries(picks, min_confidence)
        
        # Optimize
        manager = BankrollManager(bankroll, risk_tolerance=risk)
        portfolio = optimizer.optimize_portfolio(entries, bankroll, risk)
        
        for entry in portfolio:
            entry['recommended_size'] = manager.get_recommended_entry_size(entry, bankroll)

    print(f"\n{'='*80}")
    print(f"OPTIMIZED PRIZEPICKS ENTRIES FOR {actual_date}")
    print(f"{'='*80}\n")
    
    print(f"Starting Bankroll: ${bankroll}")
    print(f"Risk Tolerance: {risk.capitalize()}")
    print(f"Entries Generated: {len(portfolio)}\n")
    
    tracker = PerformanceTracker()
    for i, entry in enumerate(portfolio, 1):
        print(f"\nEntry #{i} — {entry['recommended_type'].upper()}")
        print(f"  Type: {entry['entry_type']}")
        print(f"  Recommended Size: ${entry['recommended_size']}")
        print(f"  Expected Value: ${entry['ev']:.2f}")
        print(f"  ROI: {entry['roi']:.1f}%")
        print(f"  Win Probability: {entry['win_probability']*100:.1f}%")
        print(f"  Correlation Score: {entry['correlation_score']:.2f}")
        print(f"\n  Picks:")
        for pick in entry['picks']:
            print(f"    - {getattr(pick, 'player_name', '')}: {getattr(pick, 'prop_type', '')} {getattr(pick, 'recommendation', 'OVER')} {getattr(pick, 'line', 0)}")
            print(f"      Confidence: {getattr(pick, 'confidence', 0)}%")
            
        tracker.log_entry(entry)

    # Save to file
    out_path = Path("output") / f"entries_{actual_date.isoformat()}.json"
    Path("output").mkdir(exist_ok=True)
    
    def clean_entry(e):
        c = e.copy()
        c['picks'] = [getattr(p, 'to_dict', lambda: {})() for p in e['picks']]
        return c
        
    out_path.write_text(json.dumps([clean_entry(e) for e in portfolio], indent=2))
    console.print(f"\n[dim]✅ Entries saved → {out_path}[/]")

@cli.command()
@click.option('--date', required=True, help='Date to grade (YYYY-MM-DD)')
def grade(date):
    """Grade picks for a specific date"""
    from tracking.performance_tracker import PerformanceTracker
    from tracking.results_grader import ResultsGrader
    
    console.print(f"Grading entries for {date}...\n")
    tracker = PerformanceTracker()
    grader = ResultsGrader(tracker)
    count = grader.grade_date(date)
    console.print(f"[bold green]✅ Graded {count} entries back into performance tracking.[/]")

@cli.command()
@click.option('--days', default=30, help='Number of days to analyze')
def stats(days):
    """Display performance statistics"""
    from tracking.performance_tracker import PerformanceTracker
    tracker = PerformanceTracker()
    stats = tracker.calculate_statistics()
    
    print(f"\n{'='*80}")
    print(f"PERFORMANCE STATISTICS - Database Total")
    print(f"{'='*80}\n")
    
    print(f"Total Entries: {stats['total_entries']}")
    print(f"Win Rate: {stats['win_rate']:.1f}%")
    print(f"Total Wagered: ${stats['total_wagered']:.2f}")
    print(f"Total Profit: ${stats['total_profit']:+.2f}")
    print(f"ROI: {stats['roi']:+.1f}%")

@cli.command()
@click.option('--date', required=True, help='Historical date (YYYY-MM-DD)')
def demo(date):
    """Run demo picks on historical date"""
    from utils.demo_mode import DemoMode
    from tracking.performance_tracker import PerformanceTracker
    
    console.print(f"Running demo picks for {date}...\n")
    demo_mode = DemoMode(PerformanceTracker())
    demo_mode.run_demo_picks(date)
    console.print(f"\n[green]Demo picks generated. Grade them later.[/]")

@cli.command()
@click.option('--start-date', required=True)
@click.option('--end-date', required=True)
@click.option('--bankroll', default=150.0)
def backtest(start_date, end_date, bankroll):
    """Run backtest over date range"""
    from utils.demo_mode import DemoMode
    from tracking.performance_tracker import PerformanceTracker
    
    console.print(f"Running backtest from {start_date} to {end_date}...")
    console.print(f"Starting bankroll: ${bankroll}\n")
    
    demo_mode = DemoMode(PerformanceTracker())
    results = demo_mode.run_backtest(start_date, end_date, bankroll)
    
    final_bankroll = results[-1]['bankroll'] if results else bankroll
    profit = final_bankroll - bankroll
    roi = (profit / bankroll) * 100 if bankroll > 0 else 0
    
    print(f"\n{'='*80}")
    print(f"BACKTEST RESULTS")
    print(f"{'='*80}\n")
    print(f"Starting Bankroll: ${bankroll}")
    print(f"Final Bankroll: ${final_bankroll:.2f}")
    print(f"Total Profit: ${profit:+.2f}")
    print(f"ROI: {roi:+.1f}%")
    print(f"Trading Days: {len(results)}")
    
    demo_mode.visualize_backtest_results(results)
    console.print(f"\n[dim]Chart saved to: output/backtest_results.png[/]")

@cli.command()
def reset_learning():
    """Wipe AI weights and learning history"""
    from analysis.teacher import Teacher
    Teacher().reset_learning()
    console.print("[bold green]✅ AI learning history and multipliers have been reset.[/]")

@cli.command()
@click.option('--host', default="0.0.0.0")
@click.option('--port', default=8000, type=int)
def serve(host, port):
    """Start FastAPI REST server"""
    import uvicorn
    from api.app import app
    console.print(f"\n[bold cyan]🚀 Starting API server[/] at http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")

def __parse_sources(source: str | None) -> list[str] | None:
    if not source: return None
    s = source.strip().lower()
    if s in ("pp", "prizepicks"): return ["PrizePicks"]
    if s in ("dk", "draftkings"): return ["DraftKings"]
    return None

if __name__ == '__main__':
    try:
        cli()
    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted.[/]")
        sys.exit(0)
