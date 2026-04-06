"""
tracking/performance_tracker.py — SQLite-backed performance tracking system.
"""
import sqlite3
import uuid
import os
from datetime import datetime
from typing import Dict, Any, List

class PerformanceTracker:
    def __init__(self, db_path='tracking/performance.db'):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._init_database()
        
    def _init_database(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS entries (
                entry_id TEXT PRIMARY KEY,
                date TEXT,
                entry_type TEXT,
                num_picks INTEGER,
                entry_size REAL,
                win_probability REAL,
                ev REAL,
                correlation_score REAL,
                result TEXT DEFAULT 'pending',
                num_hits INTEGER DEFAULT 0,
                profit_loss REAL DEFAULT 0,
                graded_date TEXT,
                is_demo BOOLEAN DEFAULT 0
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS entry_picks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_id TEXT,
                player_name TEXT,
                prop_type TEXT,
                line REAL,
                over_under TEXT,
                confidence REAL,
                actual_value REAL DEFAULT NULL,
                was_correct INTEGER DEFAULT NULL,
                FOREIGN KEY(entry_id) REFERENCES entries(entry_id)
            )
        ''')
        # Migrate existing DBs that don't have these columns yet
        try:
            c.execute("ALTER TABLE entry_picks ADD COLUMN actual_value REAL DEFAULT NULL")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE entry_picks ADD COLUMN was_correct INTEGER DEFAULT NULL")
        except Exception:
            pass
        conn.commit()
        conn.close()

    def log_entry(self, entry_data: Dict[str, Any], is_demo: bool = False) -> str:
        entry_id = str(uuid.uuid4())
        date_str = datetime.now().isoformat()
        
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute('''
            INSERT INTO entries 
            (entry_id, date, entry_type, num_picks, entry_size, win_probability, ev, correlation_score, is_demo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            entry_id, date_str, entry_data.get('entry_type', ''), len(entry_data.get('picks', [])),
            entry_data.get('entry_amount', 0), entry_data.get('win_probability', 0), 
            entry_data.get('ev', 0), entry_data.get('correlation_score', 0), int(is_demo)
        ))
        
        for pick in entry_data.get('picks', []):
            c.execute('''
                INSERT INTO entry_picks 
                (entry_id, player_name, prop_type, line, over_under, confidence)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                entry_id, getattr(pick, 'player_name', ''), getattr(pick, 'prop_type', ''),
                getattr(pick, 'line', 0.0), getattr(pick, 'recommendation', getattr(pick, 'over_under', 'OVER')),
                getattr(pick, 'confidence', 0.0)
            ))
            
        conn.commit()
        conn.close()
        return entry_id

    def grade_entry(self, entry_id: str, results: List[str], payout_multiplier: float) -> str:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute('SELECT entry_type, num_picks, entry_size FROM entries WHERE entry_id = ?', (entry_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            return 'not_found'
            
        entry_type, num_picks, entry_size = row
        num_hits = sum(1 for r in results if r == 'hit')
        
        won = False
        if entry_type.startswith('power'):
            won = (num_hits == num_picks)
        else:
            won = (num_hits >= (num_picks - 1))
            
        profit = (entry_size * (payout_multiplier - 1)) if won else -entry_size
        status = 'win' if won else 'loss'
        date_str = datetime.now().isoformat()
        
        c.execute('''
            UPDATE entries 
            SET result = ?, num_hits = ?, profit_loss = ?, graded_date = ?
            WHERE entry_id = ?
        ''', (status, num_hits, profit, date_str, entry_id))
        
        conn.commit()
        conn.close()
        return status

    def get_entries(self, date: str = None, is_demo: bool = False, graded: bool = False) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        query = "SELECT * FROM entries WHERE is_demo = ?"
        params = [int(is_demo)]
        
        if date:
            query += " AND date LIKE ?"
            params.append(f"{date}%")
            
        if not graded:
            query += " AND result = 'pending'"
            
        c.execute(query, params)
        rows = c.fetchall()
        
        entries = []
        for row in rows:
            entry = dict(row)
            # fetch picks
            c.execute("SELECT * FROM entry_picks WHERE entry_id = ?", (entry['entry_id'],))
            pick_rows = c.fetchall()
            
            # mock objects for compatibility
            class TrackedPick:
                def __init__(self, r):
                    self.player_name = r['player_name']
                    self.prop_type = r['prop_type']
                    self.line = r['line']
                    self.over_under = r['over_under']
                    self.confidence = r['confidence']
                    
            entry['picks'] = [TrackedPick(dict(pr)) for pr in pick_rows]
            entries.append(entry)
            
        conn.close()
        return entries
        
    def calculate_statistics(self, date_range=None) -> Dict[str, Any]:
        """Calculates global metrics for dashboard."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT COUNT(*), SUM(CASE WHEN result='win' THEN 1 ELSE 0 END), SUM(entry_size), SUM(profit_loss) FROM entries WHERE result != 'pending'")
        row = c.fetchone()
        conn.close()
        
        total = row[0] or 0
        wins = row[1] or 0
        return {
            'total_entries': total,
            'win_rate': (wins/total)*100 if total > 0 else 0,
            'total_wagered': row[2] or 0.0,
            'total_profit': row[3] or 0.0,
            'roi': ((row[3] or 0) / (row[2] or 1)) * 100 if (row[2] or 0) > 0 else 0
        }
    def get_current_bankroll(self, starting_bankroll: float) -> float:
        """Calculates the real live bankroll from the sum of all P&L in the DB."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT SUM(profit_loss) FROM entries WHERE result != 'pending' AND is_demo = 0")
        row = c.fetchone()
        conn.close()
        net_pl = row[0] or 0.0
        return round(starting_bankroll + net_pl, 2)

    def record_pick_result(self, entry_id: str, player_name: str, actual_value: float, was_correct: bool):
        """Fix 7: Persist actual graded values to entry_picks for Teacher to consume."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''
            UPDATE entry_picks
            SET actual_value = ?, was_correct = ?
            WHERE entry_id = ? AND player_name = ?
        ''', (actual_value, int(was_correct), entry_id, player_name))
        conn.commit()
        conn.close()

    def get_graded_picks_for_learning(self, date_str: str = None) -> list:
        """Returns all graded entry_picks with actual_value for Teacher consumption."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        query = '''
            SELECT ep.player_name, ep.prop_type, ep.line, ep.over_under,
                   ep.confidence, ep.actual_value, ep.was_correct, e.date
            FROM entry_picks ep
            JOIN entries e ON ep.entry_id = e.entry_id
            WHERE ep.actual_value IS NOT NULL
        '''
        params = []
        if date_str:
            query += " AND e.date LIKE ?"
            params.append(f"{date_str}%")
        c.execute(query, params)
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows
