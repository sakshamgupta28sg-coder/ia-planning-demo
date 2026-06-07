"""
SQLite persistence layer for Working Plan overrides and snapshots.

Single file: planning.db (sits next to this module).
No external dependencies — sqlite3 ships with Python.
"""

import sqlite3
import json
import os
from typing import Dict, List, Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "planning.db")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist. Safe to call on every startup."""
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS overrides (
                key  TEXT PRIMARY KEY,
                data TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS snapshots (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                name            TEXT    NOT NULL,
                created_at      TEXT    NOT NULL,
                overrides_count INTEGER NOT NULL,
                overrides_data  TEXT    NOT NULL,
                summary_data    TEXT    NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sku_settings (
                hierarchy_code  INTEGER PRIMARY KEY,
                data            TEXT    NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS channel_settings (
                key   TEXT PRIMARY KEY,
                data  TEXT NOT NULL
            )
        """)
        conn.commit()


# ── Channel Settings CRUD ──────────────────────────────────────────────────────

def db_get_all_channel_settings() -> Dict[str, Dict]:
    """Return all per-SKU×channel settings keyed by '{hc}_{channel}'."""
    with _conn() as conn:
        rows = conn.execute("SELECT key, data FROM channel_settings").fetchall()
    return {r["key"]: json.loads(r["data"]) for r in rows}


def db_upsert_channel_setting(key: str, data: Dict):
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO channel_settings (key, data) VALUES (?, ?)",
            (key, json.dumps(data)),
        )
        conn.commit()


# ── SKU Settings CRUD ──────────────────────────────────────────────────────────

def db_get_all_sku_settings() -> Dict[int, Dict]:
    """Return all per-SKU setting overrides keyed by hierarchy_code."""
    with _conn() as conn:
        rows = conn.execute("SELECT hierarchy_code, data FROM sku_settings").fetchall()
    return {r["hierarchy_code"]: json.loads(r["data"]) for r in rows}


def db_upsert_sku_setting(hierarchy_code: int, data: Dict):
    """Insert or replace settings for one SKU."""
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO sku_settings (hierarchy_code, data) VALUES (?, ?)",
            (hierarchy_code, json.dumps(data)),
        )
        conn.commit()


# ── Override CRUD ─────────────────────────────────────────────────────────────

def db_get_overrides() -> Dict[str, Dict]:
    """Load all overrides from DB. Returns empty dict if none saved."""
    with _conn() as conn:
        rows = conn.execute("SELECT key, data FROM overrides").fetchall()
    return {r["key"]: json.loads(r["data"]) for r in rows}


def db_upsert_override(key: str, data: Dict):
    """Insert or replace a single override entry."""
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO overrides (key, data) VALUES (?, ?)",
            (key, json.dumps(data)),
        )
        conn.commit()


def db_clear_overrides():
    """Delete all overrides (reset)."""
    with _conn() as conn:
        conn.execute("DELETE FROM overrides")
        conn.commit()


def db_replace_overrides(overrides: Dict[str, Dict]):
    """Atomically replace all overrides — used by snapshot restore."""
    with _conn() as conn:
        conn.execute("DELETE FROM overrides")
        for key, data in overrides.items():
            conn.execute(
                "INSERT INTO overrides (key, data) VALUES (?, ?)",
                (key, json.dumps(data)),
            )
        conn.commit()


# ── Snapshot CRUD ─────────────────────────────────────────────────────────────

def db_list_snapshots() -> List[Dict]:
    """Return all snapshots ordered by creation. Excludes overrides blob (large)."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, name, created_at, overrides_count, summary_data "
            "FROM snapshots ORDER BY id"
        ).fetchall()
    return [
        {
            "id":              r["id"],
            "name":            r["name"],
            "created_at":      r["created_at"],
            "overrides_count": r["overrides_count"],
            "summary":         json.loads(r["summary_data"]),
        }
        for r in rows
    ]


def db_get_snapshot(snap_id: int) -> Optional[Dict]:
    """Return a single snapshot including its full overrides blob (for restore)."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT id, name, created_at, overrides_count, overrides_data, summary_data "
            "FROM snapshots WHERE id = ?",
            (snap_id,),
        ).fetchone()
    if not row:
        return None
    return {
        "id":              row["id"],
        "name":            row["name"],
        "created_at":      row["created_at"],
        "overrides_count": row["overrides_count"],
        "overrides":       json.loads(row["overrides_data"]),
        "summary":         json.loads(row["summary_data"]),
    }


def db_insert_snapshot(name: str, created_at: str, overrides_count: int,
                       overrides: Dict, summary: Dict) -> Dict:
    """Insert snapshot row, return the new record (id from AUTOINCREMENT)."""
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO snapshots "
            "(name, created_at, overrides_count, overrides_data, summary_data) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, created_at, overrides_count,
             json.dumps(overrides), json.dumps(summary)),
        )
        snap_id = cur.lastrowid
        conn.commit()
    return {
        "id":              snap_id,
        "name":            name,
        "created_at":      created_at,
        "overrides_count": overrides_count,
        "summary":         summary,
    }


def db_delete_snapshot(snap_id: int) -> bool:
    """Delete snapshot by id. Returns True if a row was deleted."""
    with _conn() as conn:
        cur = conn.execute("DELETE FROM snapshots WHERE id = ?", (snap_id,))
        conn.commit()
    return cur.rowcount > 0


def db_batch_upsert_overrides(updates: Dict[str, Dict]):
    """Insert or replace multiple override entries in a single transaction (fast path)."""
    with _conn() as conn:
        for key, data in updates.items():
            conn.execute(
                "INSERT OR REPLACE INTO overrides (key, data) VALUES (?, ?)",
                (key, json.dumps(data)),
            )
        conn.commit()
