"""
main.py — CLI entry point for the MLB Betting Analysis system.

Modes:
    run       — Run full pick generation for today (or a given date)
    serve     — Start FastAPI server
    schedule  — Start APScheduler daemon (runs picks daily at 11 AM ET)
    picks     — Print picks to console (alias for run but pretty-printed)

Usage:
    python main.py run
    python main.py run --date 2025-04-01 --min-confidence 60
    python main.py serve
    python main.py serve --host 127.0.0.1 --port 8080
    python main.py schedule
    python main.py picks --source prizepicks
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich import box

console = Console()


def cmd_run(args: argparse.Namespace) -> None:
    """Generate picks and write to JSON file."""
    from picks.pick_generator import generate_daily_picks
    from picks.parlay_builder import build_parlays

    date = None
    if args.date and args.date.lower() != "today":
        date = datetime.date.fromisoformat(args.date)

    console.print(f"\n[bold cyan]🎯 MLB Betting Analysis[/] — {date or datetime.date.today()}\n")

    with console.status("Fetching lines and running models…"):
        picks = generate_daily_picks(
            date=date,
            min_confidence=args.min_confidence,
            sources=_parse_sources(args.source),
        )
        parlays = build_parlays(picks)

    if not picks:
        console.print("[yellow]⚠ No qualifying picks today.[/]")
        return

    # ── Print picks table ────────────────────────────────────────────────────
    table = Table(title=f"Top Picks — {date or datetime.date.today()}", box=box.ROUNDED)
    table.add_column("Player", style="bold white")
    table.add_column("Prop")
    table.add_column("Line", justify="center")
    table.add_column("Rec", justify="center")
    table.add_column("Conf", justify="center")
    table.add_column("Source")

    for p in picks[:25]:
        conf_color = "green" if p.confidence >= 70 else ("yellow" if p.confidence >= 60 else "white")
        rec_color = "green" if p.recommendation == "OVER" else "red"
        table.add_row(
            p.player_name,
            p.prop_type,
            str(p.line),
            f"[{rec_color}]{p.recommendation}[/]",
            f"[{conf_color}]{p.confidence}[/]",
            p.source,
        )
    console.print(table)

    # ── Print parlay summary ─────────────────────────────────────────────────
    if parlays["power_plays"]:
        console.print("\n[bold cyan]⚡ Top Power Plays (2-leg)[/]")
        for i, pp in enumerate(parlays["power_plays"], 1):
            legs = ", ".join(f"{l.player_name} {l.recommendation} {l.prop_type} ({l.line})" for l in pp.legs)
            console.print(f"  {i}. [{pp.combined_score:.0f}] {legs}")

    if parlays["flex_plays"]:
        console.print("\n[bold magenta]🎰 Top Flex Plays[/]")
        for i, fp in enumerate(parlays["flex_plays"], 1):
            legs = " | ".join(f"{l.player_name} {l.recommendation}" for l in fp.legs)
            console.print(f"  {i}. [{fp.num_legs}-leg, conf={fp.avg_confidence:.0f}] {legs}")

    # ── Write JSON output ────────────────────────────────────────────────────
    today = date or datetime.date.today()
    out_path = Path("output") / f"picks_{today.isoformat()}.json"
    Path("output").mkdir(exist_ok=True)
    payload = {
        "generated_at": datetime.datetime.utcnow().isoformat(),
        "date": today.isoformat(),
        "picks_count": len(picks),
        "picks": [p.to_dict() for p in picks],
        "parlays": {
            "power_plays": [p.to_dict() for p in parlays["power_plays"]],
            "flex_plays":  [p.to_dict() for p in parlays["flex_plays"]],
        },
    }
    out_path.write_text(json.dumps(payload, indent=2))
    console.print(f"\n[dim]✅ Saved {len(picks)} picks → {out_path}[/]")


def cmd_serve(args: argparse.Namespace) -> None:
    """Start the FastAPI server."""
    import uvicorn
    from api.app import app

    console.print(f"\n[bold cyan]🚀 Starting API server[/] at http://{args.host}:{args.port}")
    console.print(f"  Docs → [link]http://{args.host}:{args.port}/docs[/link]\n")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


def cmd_schedule(args: argparse.Namespace) -> None:
    """Start the APScheduler daemon."""
    from scheduler import start_scheduler
    start_scheduler()


# ─────────────────────────────────────────────────────────────────────────────
# Argument Parsing
# ─────────────────────────────────────────────────────────────────────────────

def _parse_sources(source: str | None) -> list[str] | None:
    if not source:
        return None
    s = source.strip().lower()
    if s in ("pp", "prizepicks"):
        return ["PrizePicks"]
    if s in ("dk", "draftkings"):
        return ["DraftKings"]
    return None  # all sources


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mlb-betting",
        description="MLB Betting Analysis — pick generation, API server, and scheduler",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # run
    run_p = sub.add_parser("run", help="Generate picks for today (or a given date)")
    run_p.add_argument("--date", default="today", help="YYYY-MM-DD or 'today'")
    run_p.add_argument("--min-confidence", type=int, default=55)
    run_p.add_argument("--source", default=None, help="prizepicks | draftkings | all")
    run_p.set_defaults(func=cmd_run)

    # picks (alias for run)
    picks_p = sub.add_parser("picks", help="Alias for 'run'")
    picks_p.add_argument("--date", default="today")
    picks_p.add_argument("--min-confidence", type=int, default=55)
    picks_p.add_argument("--source", default=None)
    picks_p.set_defaults(func=cmd_run)

    # serve
    serve_p = sub.add_parser("serve", help="Start FastAPI REST server")
    serve_p.add_argument("--host", default="0.0.0.0")
    serve_p.add_argument("--port", type=int, default=8000)
    serve_p.set_defaults(func=cmd_serve)

    # schedule
    sched_p = sub.add_parser("schedule", help="Start APScheduler daemon")
    sched_p.set_defaults(func=cmd_schedule)

    return parser


if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted.[/]")
        sys.exit(0)
