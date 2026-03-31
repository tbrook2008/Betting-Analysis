"""
analysis/teacher.py — The "Brain" for autonomous learning.
Scrapes yesterday's box scores, grades accuracy, and tunes multipliers.
"""
import datetime
import json
import os
from pathlib import Path
from typing import Dict, List, Any

from data import mlb_client as mlb
from utils.logger import get_logger

log = get_logger(__name__)

REGISTRY_PATH = Path("data/dynamic_weights.json")

class Teacher:
    def __init__(self):
        self.registry = self._load_registry()

    def _load_registry(self) -> Dict[str, Any]:
        if not REGISTRY_PATH.exists():
            return {
                "last_run_date": "1900-01-01",
                "learning_history": [],
                "multipliers": {
                    "pitcher_ks": 1.0,
                    "hits": 1.0,
                    "home_runs": 1.0,
                    "total_bases": 1.0,
                    "game_totals": 1.0
                }
            }
        return json.loads(REGISTRY_PATH.read_text())

    def _save_registry(self):
        REGISTRY_PATH.parent.mkdir(exist_ok=True)
        REGISTRY_PATH.write_text(json.dumps(self.registry, indent=2))

    def is_first_run_today(self) -> bool:
        """Check if we've already 'taught' the AI today."""
        last_run = self.registry.get("last_run_date")
        today_str = datetime.date.today().isoformat()
        return last_run != today_str

    def reset_learning(self):
        """Wipe the AI's multipliers back to 1.0."""
        self.registry["multipliers"] = {k: 1.0 for k in self.registry["multipliers"]}
        self.registry["learning_history"].append({
            "timestamp": datetime.datetime.now().isoformat(),
            "action": "RESET_ALL_WEIGHTS",
            "reason": "Manual user reset"
        })
        self._save_registry()
        log.info("AI weights have been reset to baseline.")

    def run_daily_retro(self, specific_date: datetime.date = None):
        """Evaluate yesterday's (or given date's) performance and tune weights."""
        yesterday = specific_date or (datetime.date.today() - datetime.timedelta(days=1))
        y_str = yesterday.isoformat()
        
        picks_file = Path("output") / f"picks_{y_str}.json"
        if not picks_file.exists():
            log.warning(f"No picks file found for {y_str}. Skipping retrospective.")
            self.registry["last_run_date"] = datetime.date.today().isoformat()
            self._save_registry()
            return

        log.info(f"🎓 Running AI Retrospective for {y_str}...")
        data = json.loads(picks_file.read_text())
        picks = data.get("picks", [])
        
        # Category-based tracking
        stats = {k: {"hits": 0, "total": 0} for k in self.registry["multipliers"]}
        
        for p in picks:
            category = p.get("prop_type_key")
            if category not in stats: continue
            
            # ── 1. Fetch Result from MLB API ─────────────────────────────────
            actual_value = self._get_result(p["player_name"], yesterday, category)
            if actual_value is None: continue
            
            # ── 2. Grade Success ─────────────────────────────────────────────
            is_winner = False
            line = p.get("line", 0)
            rec = p.get("recommendation", "OVER")
            
            if rec == "OVER":
                is_winner = actual_value > line
            else:
                is_winner = actual_value < line
                
            stats[category]["total"] += 1
            if is_winner:
                stats[category]["hits"] += 1

        # ── 3. Tune Multipliers ──────────────────────────────────────────────
        for cat, results in stats.items():
            if results["total"] == 0: continue
            
            accuracy = results["hits"] / results["total"]
            current_m = self.registry["multipliers"].get(cat, 1.0)
            
            # Logic: Nudge 1-2% based on accuracy above/below 55%
            nudge = 0.0
            if accuracy > 0.60: nudge = 0.02   # Hot: increment
            elif accuracy < 0.40: nudge = -0.02 # Cold: decrement
            
            new_m = current_m + nudge
            
            # User Safety Rail: Cap adjustments at ±10% (0.9 to 1.1)
            new_m = max(0.90, min(1.10, new_m))
            
            if nudge != 0:
                log.info(f"  - Tuning {cat}: {current_m:.2f} -> {new_m:.2f} (Accuracy: {accuracy:.0%})")
                self.registry["multipliers"][cat] = round(new_m, 3)
                self.registry["learning_history"].append({
                    "date": y_str,
                    "category": cat,
                    "accuracy": accuracy,
                    "multiplier": round(new_m, 3)
                })

        # Mark as run for today
        self.registry["last_run_date"] = datetime.date.today().isoformat()
        self._save_registry()
        log.info("✅ Daily teaching complete.")

    def _get_result(self, player_name: str, date: datetime.date, category: str) -> float | None:
        """Fetch the actual game stat for a player on a specific date."""
        p_id = mlb.get_player_id(player_name)
        if not p_id: return None
        
        date_str = date.isoformat()
        boxscores = mlb.get_daily_boxscores(date_str)
        if p_id not in boxscores:
            return None
            
        b_stats = boxscores[p_id]["batting"]
        p_stats = boxscores[p_id]["pitching"]
        
        if category == "pitcher_ks":
            return float(p_stats.get("strikeOuts", 0)) if "strikeOuts" in p_stats else None
            
        elif category in ["hits", "singles", "total_bases", "home_runs"]:
            if "hits" not in b_stats: return None
            
            h = float(b_stats.get("hits", 0))
            if category == "hits":
                return h
                
            d = float(b_stats.get("doubles", 0))
            t = float(b_stats.get("triples", 0))
            hr = float(b_stats.get("homeRuns", 0))
            
            if category == "home_runs":
                return hr
            if category == "singles":
                return h - d - t - hr
            if category == "total_bases":
                singles = h - d - t - hr
                return singles + (2*d) + (3*t) + (4*hr)
        
        return None

def get_multipliers() -> Dict[str, float]:
    """Helper for confidence_scorer.py."""
    t = Teacher()
    return t.registry.get("multipliers", {})
