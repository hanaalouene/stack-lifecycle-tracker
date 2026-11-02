"""Storage layer (silver/gold): append-only snapshots in SQLite plus SQL queries for the report."""

from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS snapshots (
    run_id         INTEGER NOT NULL REFERENCES runs(run_id),
    product        TEXT NOT NULL,
    label          TEXT NOT NULL,
    cycle          TEXT NOT NULL,
    release_date   TEXT,
    latest_version TEXT,
    latest_date    TEXT,
    is_lts         INTEGER NOT NULL DEFAULT 0,
    eoas_from      TEXT,
    eol_from       TEXT,
    is_eol         INTEGER NOT NULL DEFAULT 0,
    is_maintained  INTEGER NOT NULL DEFAULT 0,
    link           TEXT,
    source         TEXT NOT NULL,
    verified       INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (run_id, product, cycle)
);
"""

COLUMNS = (
    "product, label, cycle, release_date, latest_version, latest_date, is_lts, "
    "eoas_from, eol_from, is_eol, is_maintained, link, source, verified"
)


def connect(path: Path | str) -> sqlite3.Connection:
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def start_run(conn: sqlite3.Connection, now: dt.datetime | None = None) -> int:
    now = now or dt.datetime.now(dt.timezone.utc)
    cur = conn.execute("INSERT INTO runs (run_at) VALUES (?)", (now.isoformat(timespec="seconds"),))
    conn.commit()
    return cur.lastrowid


def insert_rows(conn: sqlite3.Connection, run_id: int, rows: list[dict]) -> None:
    names = [c.strip() for c in COLUMNS.split(",")]
    placeholders = ", ".join("?" for _ in range(len(names) + 1))
    conn.executemany(
        f"INSERT OR REPLACE INTO snapshots (run_id, {COLUMNS}) VALUES ({placeholders})",
        [(run_id, *[r[n] for n in names]) for r in rows],
    )
    conn.commit()


def previous_run_id(conn: sqlite3.Connection, run_id: int) -> int | None:
    row = conn.execute("SELECT MAX(run_id) AS r FROM runs WHERE run_id < ?", (run_id,)).fetchone()
    return row["r"]


def _all(conn: sqlite3.Connection, sql: str, params: dict) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


# --- gold queries ----------------------------------------------------------------------------

def new_cycles(conn, cur_id: int, prev_id: int) -> list[dict]:
    """Release cycles that did not exist in the previous run (e.g. a new major/minor line)."""
    return _all(
        conn,
        """
        SELECT c.* FROM snapshots c
        LEFT JOIN snapshots p
               ON p.run_id = :prev AND p.product = c.product AND p.cycle = c.cycle
        WHERE c.run_id = :cur AND p.cycle IS NULL
          AND c.product IN (SELECT DISTINCT product FROM snapshots WHERE run_id = :prev)
        ORDER BY c.label, c.release_date DESC
        """,
        {"cur": cur_id, "prev": prev_id},
    )


def new_latest_versions(conn, cur_id: int, prev_id: int) -> list[dict]:
    """Existing cycles whose latest patch/minor version changed since the previous run."""
    return _all(
        conn,
        """
        SELECT c.label, c.cycle, p.latest_version AS old_version, c.latest_version AS new_version,
               c.latest_date, c.link, c.verified
        FROM snapshots c
        JOIN snapshots p ON p.run_id = :prev AND p.product = c.product AND p.cycle = c.cycle
        WHERE c.run_id = :cur AND IFNULL(c.latest_version, '') <> IFNULL(p.latest_version, '')
        ORDER BY c.label, c.cycle DESC
        """,
        {"cur": cur_id, "prev": prev_id},
    )


def eol_date_changes(conn, cur_id: int, prev_id: int) -> list[dict]:
    """Cycles whose end-of-life date was added, moved or removed."""
    return _all(
        conn,
        """
        SELECT c.label, c.cycle, p.eol_from AS old_eol, c.eol_from AS new_eol
        FROM snapshots c
        JOIN snapshots p ON p.run_id = :prev AND p.product = c.product AND p.cycle = c.cycle
        WHERE c.run_id = :cur AND c.eol_from IS NOT p.eol_from
        ORDER BY c.label, c.cycle DESC
        """,
        {"cur": cur_id, "prev": prev_id},
    )


def newly_eol(conn, cur_id: int, prev_id: int) -> list[dict]:
    """Cycles that reached end of life since the previous run."""
    return _all(
        conn,
        """
        SELECT c.label, c.cycle, c.eol_from, c.latest_version
        FROM snapshots c
        JOIN snapshots p ON p.run_id = :prev AND p.product = c.product AND p.cycle = c.cycle
        WHERE c.run_id = :cur AND c.is_eol = 1 AND p.is_eol = 0
        ORDER BY c.eol_from, c.label
        """,
        {"cur": cur_id, "prev": prev_id},
    )


def upcoming_eol(conn, cur_id: int, today: dt.date, days: int) -> list[dict]:
    """Supported cycles that will reach end of life within the next `days` days."""
    limit = today + dt.timedelta(days=days)
    return _all(
        conn,
        """
        SELECT label, cycle, latest_version, eoas_from, eol_from, verified
        FROM snapshots
        WHERE run_id = :cur AND is_eol = 0 AND eol_from IS NOT NULL
          AND eol_from BETWEEN :today AND :limit
        ORDER BY eol_from, label
        """,
        {"cur": cur_id, "today": today.isoformat(), "limit": limit.isoformat()},
    )


def recently_eol(conn, cur_id: int, today: dt.date, days: int = 60) -> list[dict]:
    """Cycles that reached end of life in the last `days` days (still worth knowing about)."""
    since = today - dt.timedelta(days=days)
    return _all(
        conn,
        """
        SELECT label, cycle, latest_version, eol_from, verified
        FROM snapshots
        WHERE run_id = :cur AND is_eol = 1 AND eol_from >= :since
        ORDER BY eol_from DESC, label
        """,
        {"cur": cur_id, "since": since.isoformat()},
    )


def supported_now(conn, cur_id: int) -> list[dict]:
    """Current supported release lines with their latest version."""
    return _all(
        conn,
        """
        SELECT label, cycle, latest_version, latest_date, is_lts, eol_from, source, verified
        FROM snapshots
        WHERE run_id = :cur AND is_eol = 0
        ORDER BY label, release_date DESC, cycle DESC
        """,
        {"cur": cur_id},
    )
