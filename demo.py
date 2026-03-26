"""
demo.py — A quick demonstration of the MLB Betting Analysis engine.
Analyzes a single player to show signals and confidence scoring in seconds.
"""
from __future__ import annotations
import datetime
from rich.console import Console
from rich.table import Table
from rich import box

from picks.pick_generator import _build_game_context, _score_line
from data.mlb_client import get_schedule

console = Console()

def run_demo(player_name: str = "Aaron Judge"):
    console.print(f"\n[bold cyan]🎯 MLB Betting Analysis Demo — {player_name}[/]\n")
    
    # 1. Setup mock line
    mock_line = {
        "player_name": player_name,
        "prop_type": "Home Runs",
        "line_score": 0.5,
        "source": "Demo",
        "team": "New York Yankees",
        "opponent": "San Francisco Giants",
        "game_time": datetime.datetime.now().isoformat()
    }
    
    # 2. Get real game context if possible
    schedule = get_schedule()
    game_ctx = _build_game_context(schedule)
    
    # 3. Fallback game context if no game today
    if str(mock_line["team"]).lower() not in game_ctx:
        game_ctx[str(mock_line["team"]).lower()] = {
            "venue": "Yankee Stadium",
            "away_pitcher_name": "Logan Webb",
            "away_pitcher_id": 660271,
            "is_home": True,
            "opponent": "SF"
        }

    # 4. Score
    with console.status(f"Analyzing {player_name} vs Logan Webb…"):
        pick = _score_line(mock_line, game_ctx)
    
    if not pick:
        console.print("[red]❌ Could not generate signals for demo.[/]")
        return

    # 5. Display
    table = Table(box=box.DOUBLE)
    table.add_column("Category", style="cyan")
    table.add_column("Value", style="white")
    
    table.add_row("Player", pick.player_name)
    table.add_row("Prop", f"{pick.prop_type} {pick.line}")
    table.add_row("Recommendation", f"[bold {'green' if pick.recommendation == 'OVER' else 'red'}]{pick.recommendation}[/]")
    table.add_row("Confidence", f"{pick.confidence}/100")
    
    console.print(table)
    
    console.print("\n[bold]Reasoning:[/]")
    for r in pick.reasoning:
        console.print(f"  {r}")

if __name__ == "__main__":
    run_demo("Aaron Judge")
