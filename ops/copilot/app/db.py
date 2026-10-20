import json
import sqlite3
from contextlib import contextmanager

from app import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS deploys (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sha TEXT NOT NULL,
  image TEXT NOT NULL DEFAULT '',
  commit_message TEXT NOT NULL DEFAULT '',
  files_changed TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'succeeded',
  kind TEXT NOT NULL DEFAULT 'deploy',
  deployed_at REAL NOT NULL,
  marked_bad INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS incidents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  alert_name TEXT NOT NULL,
  created_at REAL NOT NULL,
  alert_start REAL NOT NULL,
  alert_resolved_at REAL,
  status TEXT NOT NULL,
  suspect_sha TEXT,
  confidence TEXT NOT NULL,
  action TEXT NOT NULL,
  previous_good_sha TEXT,
  analysis_json TEXT NOT NULL,
  evidence_json TEXT NOT NULL,
  report_json TEXT NOT NULL,
  report_source TEXT NOT NULL,
  report_note TEXT NOT NULL DEFAULT '',
  is_replay INTEGER NOT NULL DEFAULT 0,
  replay_name TEXT,
  first_viewed_at REAL,
  rollback_detail TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS decisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  incident_id INTEGER NOT NULL,
  decision TEXT NOT NULL,
  reason TEXT NOT NULL,
  seconds_to_decide REAL NOT NULL,
  confirmed_fast INTEGER NOT NULL DEFAULT 0,
  decided_at REAL NOT NULL
);
"""

JSON_COLUMNS = ("analysis_json", "evidence_json", "report_json")


@contextmanager
def session():
    conn = sqlite3.connect(config.settings.db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with session() as conn:
        conn.executescript(SCHEMA)


def incident_row(row: sqlite3.Row | None) -> dict | None:
    """Row -> dict with the JSON columns decoded (keys: analysis, evidence, report)."""
    if row is None:
        return None
    d = dict(row)
    for col in JSON_COLUMNS:
        d[col.removesuffix("_json")] = json.loads(d.pop(col))
    return d
