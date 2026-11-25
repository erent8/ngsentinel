"""Analysis history stored in SQLite (runs/history.sqlite)."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  sample TEXT NOT NULL,
  created_at TEXT NOT NULL,
  finished_at TEXT,
  state TEXT NOT NULL,
  overall TEXT,
  paired INTEGER NOT NULL,
  reads_before INTEGER,
  reads_after INTEGER,
  q30_before REAL,
  q30_after REAL,
  retention_pct REAL,
  engines TEXT,
  run_dir TEXT NOT NULL,
  error TEXT
);
"""


class History:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.db_path, timeout=30)
        c.row_factory = sqlite3.Row
        return c

    def add(self, run_id: str, sample: str, created_at: str, paired: bool, run_dir: str) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO runs(run_id, sample, created_at, state, paired, run_dir) VALUES (?,?,?,?,?,?)",
                      (run_id, sample, created_at, "queued", int(paired), run_dir))

    def update(self, run_id: str, **fields) -> None:
        if not fields:
            return
        if "engines" in fields and not isinstance(fields["engines"], str):
            fields["engines"] = json.dumps(fields["engines"])
        cols = ", ".join(f"{k}=?" for k in fields)
        with self._conn() as c:
            c.execute(f"UPDATE runs SET {cols} WHERE run_id=?", (*fields.values(), run_id))

    def get(self, run_id: str) -> Optional[dict]:
        with self._conn() as c:
            r = c.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return _row(r) if r else None

    def list(self, limit: int = 200) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [_row(r) for r in rows]

    def delete(self, run_id: str) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM runs WHERE run_id=?", (run_id,))


def _row(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["paired"] = bool(d["paired"])
    try:
        d["engines"] = json.loads(d["engines"]) if d.get("engines") else {}
    except json.JSONDecodeError:
        d["engines"] = {}
    return d
