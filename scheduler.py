"""
scheduler.py — APScheduler daemon for daily automated pick runs.

Runs pick generation N minutes before the first game each day,
writes results to output/picks_YYYY-MM-DD.json.

Usage:
    python main.py schedule
"""
from __future__ import annotations

import datetime
import json
import os
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

import config
from picks.pick_generator import generate_daily_picks
from picks.parlay_builder import build_parlays
from utils.logger import get_logger

log = get_logger(__name__)

scheduler = BlockingScheduler(timezone="America/New_York")


def run_daily_picks() -> None:
    """Generate picks and write JSON output for today."""
    today = datetime.date.today()
    log.info(f"[Scheduler] Running daily picks for {today}…")

    picks = generate_daily_picks(date=today)
    parlays = build_parlays(picks)

    output_path = config.OUTPUT_DIR / f"picks_{today.isoformat()}.json"
    payload = {
        "generated_at": datetime.datetime.utcnow().isoformat(),
        "date": today.isoformat(),
        "picks_count": len(picks),
        "picks": [p.to_dict() for p in picks],
        "parlays": {
            "power_plays": [p.to_dict() for p in parlays["power_plays"]],
            "flex_plays": [p.to_dict() for p in parlays["flex_plays"]],
        },
    }

    output_path.write_text(json.dumps(payload, indent=2))
    log.info(f"[Scheduler] Wrote {len(picks)} picks → {output_path}")


def start_scheduler() -> None:
    """Start the APScheduler blocking scheduler."""
    # Default: 11:00 AM ET (before most day games / well before prime time)
    # Adjust SCHEDULER_LEAD_MINUTES in .env to tune
    trigger = CronTrigger(hour=11, minute=00, timezone="America/New_York")

    scheduler.add_job(
        run_daily_picks,
        trigger=trigger,
        id="daily_picks",
        name="Daily MLB Pick Generation",
        replace_existing=True,
    )

    log.info("⏰ Scheduler started. Daily picks will run at 11:00 AM ET.")
    log.info("Press Ctrl+C to stop.")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler stopped.")
