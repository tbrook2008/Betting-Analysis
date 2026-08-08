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
@click.option('--bankroll', default=None, type=float, help='Current bankroll (overrides config)')
@click.option('--risk', default='conservative', help='Risk tolerance')
@click.option('--source', default=None, help='prizepicks | draftkings | all')
@click.option('--sport', default='mlb', help='mlb | nba')
def run(date, min_confidence, bankroll, risk, source, sport):
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

    console.print(f"\n[bold cyan]🎯 PrizePicks EV Optimization[/] — {actual_date} ({sport.upper()})\n")

    with console.status("Fetching lines and running base models…"):
        picks = generate_daily_picks(
            date=actual_date,
            min_confidence=min_confidence,
            sources=__parse_sources(source),
            sport=sport,
        )

    if not picks:
        console.print("[yellow]⚠ No qualifying picks today.[/]")
        return
        
    top_picks = [p.to_dict() for p in picks if getattr(p, 'confidence', 0) >= 75]
    if top_picks:
        from utils.gemini_client import vet_top_picks
        with console.status("🧠 Gemini AI Expert Vetting in progress (batching top picks)..."):
            ai_analysis = vet_top_picks(top_picks)
            
            console.print("\n[bold magenta]🤖 Gemini Expert Analysis:[/]")
            approved_players = set()
            for res in ai_analysis:
                player = res.get("player_name")
                status = res.get("status")
                reason = res.get("reasoning")
                if status == "APPROVED":
                    console.print(f"[green]✅ {player}: {reason}[/]")
                    approved_players.add(player)
                else:
                    console.print(f"[red]❌ {player} (REJECTED): {reason}[/]")
            
            if ai_analysis:
                # Keep picks that were either APPROVED by Gemini, or weren't sent to Gemini (confidence < 75)
                vetted_players = {res.get("player_name") for res in ai_analysis}
                picks = [
                    p for p in picks 
                    if getattr(p, 'player_name', '') not in vetted_players 
                    or getattr(p, 'player_name', '') in approved_players
                ]
            console.print("\n")
        
    # Fix 4: Auto-read live bankroll from DB, using --bankroll as starting capital
    from config import BANKROLL_CONFIG
    if bankroll is None:
        bankroll = BANKROLL_CONFIG.get('default_starting_bankroll', 150.0)
    tracker_pre = PerformanceTracker()
    live_bankroll = tracker_pre.get_current_bankroll(bankroll)
    if live_bankroll != bankroll:
        console.print(f"[bold yellow]💰 Live Bankroll: ${live_bankroll:.2f}[/] (started at ${bankroll:.2f}")
    
    with console.status("Optimizing Entries and calculating correlations…"):
        corr_engine = CorrelationEngine()
        ev_calc = EVCalculator(corr_engine)
        optimizer = EntryOptimizer(ev_calc)
        entries = optimizer.generate_all_entries(picks, min_confidence)
        manager = BankrollManager(live_bankroll, risk_tolerance=risk)
        portfolio = optimizer.optimize_portfolio(entries, live_bankroll, risk)
        for entry in portfolio:
            entry['recommended_size'] = manager.get_recommended_entry_size(entry, live_bankroll)

    print(f"\n{'='*80}")
    print(f"OPTIMIZED PRIZEPICKS ENTRIES FOR {actual_date}")
    print(f"{'='*80}\n")
    print(f"Live Bankroll: ${live_bankroll:.2f}")
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

    # Save/Merge to file
    out_path = Path("output") / f"entries_{actual_date.isoformat()}.json"
    Path("output").mkdir(exist_ok=True)
    
    def clean_entry(e):
        c = e.copy()
        c['picks'] = [getattr(p, 'to_dict', lambda: {})() for p in e['picks']]
        return c
    
    current_portfolio = []
    if out_path.exists():
        try:
            current_portfolio = json.loads(out_path.read_text())
        except:
            pass
            
    # Append and filter out duplicates by entry contents
    for new_e in portfolio:
        cleaned_new = clean_entry(new_e)
        if cleaned_new not in current_portfolio:
            current_portfolio.append(cleaned_new)
            
    out_path.write_text(json.dumps(current_portfolio, indent=2))
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

@cli.command()
@click.option('--type', 'entry_type', required=True, help='e.g., power_3, flex_5')
@click.option('--amount', type=float, required=True, help='Bet amount in dollars')
@click.option('--picks', required=True, help='Comma-separated list of picks: Player:prop:line:OVER/UNDER')
def log_entry(entry_type, amount, picks):
    """Manually log a slip placed outside the system."""
    from tracking.performance_tracker import PerformanceTracker
    
    parsed_picks = []
    # Dummy class to mimic PickResult for the tracker
    class ManualPick:
        def __init__(self, name, prop, line, recommendation):
            self.player_name = name
            self.prop_type = prop
            self.line = float(line)
            self.recommendation = recommendation
            self.confidence = 75 # default
            
    for pick_str in picks.split(','):
        parts = pick_str.split(':')
        if len(parts) == 4:
            parsed_picks.append(ManualPick(parts[0].strip(), parts[1].strip(), parts[2].strip(), parts[3].strip().upper()))
        else:
            console.print(f"[red]Invalid pick format: {pick_str}[/]")
            return
            
    entry_data = {
        'entry_type': entry_type,
        'entry_amount': amount,
        'picks': parsed_picks,
        'win_probability': 0.0,
        'ev': 0.0,
        'correlation_score': 0.0
    }
    
    tracker = PerformanceTracker()
    entry_id = tracker.log_entry(entry_data, is_demo=False)
    console.print(f"[bold green]✅ Manual entry logged successfully![/] (ID: {entry_id})")

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
