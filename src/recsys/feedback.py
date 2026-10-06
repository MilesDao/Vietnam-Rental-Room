"""Real user feedback for the recommender, stored locally in SQLite (data/recsys_feedback.sqlite).

Two kinds of rows in one table:
- "impression": a listing was shown at a given rank for a given search (one row per session x query x listing);
- "up" / "down": the user pressed 👍 / 👎 on it (the latest press for a listing in a search wins).
Each row keeps the score parts the engine gave the listing at that moment, so src/recsys/ltr.py can learn
weights from exactly what the user saw. No personal data: the session id is random per browser session.
"""
import json
import os
import sqlite3
import time
from pathlib import Path

import pandas as pd

DB = Path(os.environ.get("RECSYS_FEEDBACK_DB") or Path(__file__).resolve().parents[2] / "data/recsys_feedback.sqlite")
PARTS = ["s_price", "s_value", "s_dist", "s_amenity"]


def _conn(db=None):
    db = db or DB
    Path(db).parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(db)
    c.execute("""CREATE TABLE IF NOT EXISTS events (
        session TEXT, query TEXT, listing_id TEXT, action TEXT, rank INTEGER, score REAL,
        s_price REAL, s_value REAL, s_dist REAL, s_amenity REAL, price_vnd REAL, ts REAL,
        PRIMARY KEY (session, query, listing_id, action))""")
    return c


def query_key(params):
    """Stable text id of a search (its filter values)."""
    return json.dumps(params, sort_keys=True, ensure_ascii=False, default=str)


def log(session, query, rows, action, db=None):
    """rows: DataFrame with listing_id, rank, score, the score parts and price_vnd. Re-logging replaces."""
    with _conn(db) as c:
        if action in ("up", "down"):   # a new vote replaces the opposite one
            c.executemany("DELETE FROM events WHERE session=? AND query=? AND listing_id=? AND action IN ('up','down')",
                          [(session, query, r.listing_id) for r in rows.itertuples()])
        c.executemany("INSERT OR REPLACE INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", [
            (session, query, r.listing_id, action, int(r.rank), float(r.score),
             *(float(getattr(r, p)) for p in PARTS), float(r.price_vnd), time.time()) for r in rows.itertuples()])


def votes(session, query, db=None):
    """{listing_id: 'up' | 'down'} already given in this search (to show the pressed state)."""
    with _conn(db) as c:
        return dict(c.execute("SELECT listing_id, action FROM events WHERE session=? AND query=? AND action IN ('up','down')",
                              (session, query)).fetchall())


def events(db=None):
    with _conn(db) as c:
        return pd.read_sql("SELECT * FROM events", c)
