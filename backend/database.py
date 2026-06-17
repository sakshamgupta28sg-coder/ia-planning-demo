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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS new_skus (
                hierarchy_code  INTEGER PRIMARY KEY,
                data            TEXT    NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp       TEXT    NOT NULL,
                hierarchy_code  INTEGER NOT NULL,
                channel         TEXT    NOT NULL,
                current_week    INTEGER NOT NULL,
                field           TEXT    NOT NULL,
                old_value       TEXT,
                new_value       TEXT    NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key     TEXT PRIMARY KEY,
                value   TEXT NOT NULL
            )
        """)
        # ── Warehouse (seed source-of-truth) ──────────────────────────────────
        # wp_facts holds each generated WP row as a JSON payload, indexed by
        # (hc, channel, week) for real filtering/joins. Lossless round-trip:
        # json preserves int/float/bool/null/str exactly; rowid preserves order.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS wp_facts (
                rowid           INTEGER PRIMARY KEY AUTOINCREMENT,
                hierarchy_code  INTEGER NOT NULL,
                channel         TEXT    NOT NULL,
                current_week    INTEGER NOT NULL,
                payload         TEXT    NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS ix_wp_facts_hc_ch ON wp_facts (hierarchy_code, channel)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fiscal_calendar (
                week_code       INTEGER PRIMARY KEY,
                fiscal_year     INTEGER NOT NULL,
                fiscal_week     INTEGER NOT NULL,
                start_date      TEXT    NOT NULL,
                end_date        TEXT    NOT NULL,
                fiscal_month    INTEGER NOT NULL,
                fiscal_quarter  INTEGER NOT NULL
            )
        """)
        # master_sku: catalog of every SKU (Old + New). Lifecycle dates drive the
        # active ⋈ calendar filter; tagged_to is the New→Old Disc% borrow tag (set
        # in-app, persisted here). Descriptive attrs (color/size) are display-only.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS master_sku (
                hierarchy_code     INTEGER PRIMARY KEY,
                l1_name            TEXT    NOT NULL,
                l2_name            TEXT    NOT NULL,
                sku_code           TEXT,
                color              TEXT,
                size               TEXT,
                air                REAL,
                auc                REAL,
                activation_week    INTEGER NOT NULL,
                deactivation_week  INTEGER NOT NULL,
                status_seed        TEXT    NOT NULL,
                tagged_to          INTEGER
            )
        """)
        # Migration: snapshots gained settings_data (SKU + channel-level settings
        # captured at save time) after the table first shipped. Add the column to
        # pre-existing DBs. Default '{}' = an old snapshot with no settings payload.
        cols = {r[1] for r in conn.execute("PRAGMA table_info(snapshots)").fetchall()}
        if "settings_data" not in cols:
            conn.execute("ALTER TABLE snapshots ADD COLUMN settings_data TEXT NOT NULL DEFAULT '{}'")
        conn.commit()


# ── Warehouse: WP facts seed ────────────────────────────────────────────────────

def db_replace_wp_facts(rows: List[Dict]):
    """Materialize the generated WP rows into wp_facts (full replace), order preserved."""
    with _conn() as conn:
        conn.execute("DELETE FROM wp_facts")
        conn.executemany(
            "INSERT INTO wp_facts (hierarchy_code, channel, current_week, payload) VALUES (?, ?, ?, ?)",
            [(r["hierarchy_code"], r["channel"], r["current_week"], json.dumps(r)) for r in rows],
        )
        conn.commit()


def db_load_wp_facts() -> List[Dict]:
    """Reload WP rows from the warehouse in insertion order (exact round-trip)."""
    with _conn() as conn:
        rows = conn.execute("SELECT payload FROM wp_facts ORDER BY rowid").fetchall()
    return [json.loads(r["payload"]) for r in rows]


def db_count_wp_facts() -> int:
    with _conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM wp_facts").fetchone()[0]


def db_replace_fiscal_calendar(rows: List[Dict]):
    with _conn() as conn:
        conn.execute("DELETE FROM fiscal_calendar")
        conn.executemany(
            """INSERT INTO fiscal_calendar
               (week_code, fiscal_year, fiscal_week, start_date, end_date, fiscal_month, fiscal_quarter)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [(r["week_code"], r["fiscal_year"], r["fiscal_week"], r["start_date"],
              r["end_date"], r["fiscal_month"], r["fiscal_quarter"]) for r in rows],
        )
        conn.commit()


def db_load_fiscal_calendar() -> List[Dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM fiscal_calendar ORDER BY week_code"
        ).fetchall()
    return [dict(r) for r in rows]


# ── Master SKU catalog ──────────────────────────────────────────────────────────

def db_replace_master_sku(rows: List[Dict]):
    """Seed the master_sku catalog (full replace), preserving any persisted tags."""
    with _conn() as conn:
        existing_tags = {
            r["hierarchy_code"]: r["tagged_to"]
            for r in conn.execute("SELECT hierarchy_code, tagged_to FROM master_sku").fetchall()
        }
        conn.execute("DELETE FROM master_sku")
        conn.executemany(
            """INSERT INTO master_sku
               (hierarchy_code, l1_name, l2_name, sku_code, color, size, air, auc,
                activation_week, deactivation_week, status_seed, tagged_to)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [(r["hierarchy_code"], r["l1_name"], r["l2_name"], r.get("sku_code"),
              r.get("color"), r.get("size"), r.get("air"), r.get("auc"),
              r["activation_week"], r["deactivation_week"], r["status_seed"],
              # keep a tag the user already set across restarts/reseeds
              existing_tags.get(r["hierarchy_code"], r.get("tagged_to")))
             for r in rows],
        )
        conn.commit()


def db_load_master_sku() -> List[Dict]:
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM master_sku ORDER BY hierarchy_code").fetchall()
    return [dict(r) for r in rows]


def db_set_master_tag(hierarchy_code: int, tagged_to: Optional[int]) -> bool:
    """Set/clear the New→Old Disc% borrow tag for a SKU."""
    with _conn() as conn:
        cur = conn.execute(
            "UPDATE master_sku SET tagged_to = ? WHERE hierarchy_code = ?",
            (tagged_to, hierarchy_code),
        )
        conn.commit()
    return cur.rowcount > 0


# ── Placeholders (what-if clones) ────────────────────────────────────────────────

def db_init_placeholders():
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS placeholders (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL,
                source_hc   INTEGER NOT NULL,
                created_at  TEXT    NOT NULL
            )
        """)
        conn.commit()


def db_list_placeholders() -> List[Dict]:
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM placeholders ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def db_insert_placeholder(name: str, source_hc: int, created_at: str) -> Dict:
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO placeholders (name, source_hc, created_at) VALUES (?, ?, ?)",
            (name, source_hc, created_at),
        )
        conn.commit()
        pid = cur.lastrowid
    return {"id": pid, "name": name, "source_hc": source_hc, "created_at": created_at}


def db_delete_placeholder(pid: int) -> bool:
    with _conn() as conn:
        cur = conn.execute("DELETE FROM placeholders WHERE id = ?", (pid,))
        conn.commit()
    return cur.rowcount > 0


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


def db_delete_channel_setting(key: str) -> bool:
    """Delete a channel-level setting override. Returns True if row deleted."""
    with _conn() as conn:
        cur = conn.execute("DELETE FROM channel_settings WHERE key = ?", (key,))
        conn.commit()
    return cur.rowcount > 0


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


def db_delete_sku_setting(hierarchy_code: int) -> bool:
    """Delete setting overrides for one SKU → falls back to base metrics."""
    with _conn() as conn:
        cur = conn.execute("DELETE FROM sku_settings WHERE hierarchy_code = ?", (hierarchy_code,))
        conn.commit()
    return cur.rowcount > 0


def db_replace_sku_settings(settings: Dict[int, Dict]):
    """Atomically replace ALL per-SKU setting overrides — used by snapshot restore."""
    with _conn() as conn:
        conn.execute("DELETE FROM sku_settings")
        conn.executemany(
            "INSERT INTO sku_settings (hierarchy_code, data) VALUES (?, ?)",
            [(int(hc), json.dumps(data)) for hc, data in settings.items()],
        )
        conn.commit()


def db_replace_channel_settings(settings: Dict[str, Dict]):
    """Atomically replace ALL per-SKU×channel setting overrides — used by snapshot restore."""
    with _conn() as conn:
        conn.execute("DELETE FROM channel_settings")
        conn.executemany(
            "INSERT INTO channel_settings (key, data) VALUES (?, ?)",
            [(key, json.dumps(data)) for key, data in settings.items()],
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


def db_delete_override(key: str) -> bool:
    """Delete a single override entry by key. Returns True if a row was deleted."""
    with _conn() as conn:
        cur = conn.execute("DELETE FROM overrides WHERE key = ?", (key,))
        conn.commit()
    return cur.rowcount > 0


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
            "SELECT id, name, created_at, overrides_count, overrides_data, summary_data, "
            "settings_data FROM snapshots WHERE id = ?",
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
        "settings":        json.loads(row["settings_data"] or "{}"),
    }


def db_insert_snapshot(name: str, created_at: str, overrides_count: int,
                       overrides: Dict, summary: Dict, settings: Dict = None) -> Dict:
    """Insert snapshot row, return the new record (id from AUTOINCREMENT).

    `settings` captures SKU + channel-level setting overrides (lead_time, case_pack,
    safety_weeks, target_wos) live at save time, so restore returns the full plan
    state — not just cell overrides.
    """
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO snapshots "
            "(name, created_at, overrides_count, overrides_data, summary_data, settings_data) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (name, created_at, overrides_count,
             json.dumps(overrides), json.dumps(summary), json.dumps(settings or {})),
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


def db_rename_snapshot(snap_id: int, new_name: str) -> bool:
    """Rename a snapshot. Returns True if a row was updated."""
    with _conn() as conn:
        cur = conn.execute("UPDATE snapshots SET name = ? WHERE id = ?", (new_name, snap_id))
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


# ── New SKU CRUD ───────────────────────────────────────────────────────────────

def db_get_all_new_skus() -> List[Dict]:
    """Return all user-created SKUs ordered by hierarchy_code."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT hierarchy_code, data FROM new_skus ORDER BY hierarchy_code"
        ).fetchall()
    return [{**json.loads(r["data"]), "hierarchy_code": r["hierarchy_code"]} for r in rows]


def db_get_max_new_sku_hc() -> int:
    """Return the highest hierarchy_code in new_skus (0 if table empty)."""
    with _conn() as conn:
        row = conn.execute("SELECT MAX(hierarchy_code) AS m FROM new_skus").fetchone()
    return row["m"] or 0


def db_insert_new_sku(hierarchy_code: int, data: Dict):
    """Persist a new SKU (hierarchy_code stored separately as PK)."""
    payload = {k: v for k, v in data.items() if k != "hierarchy_code"}
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO new_skus (hierarchy_code, data) VALUES (?, ?)",
            (hierarchy_code, json.dumps(payload)),
        )
        conn.commit()


def db_log_audit(hierarchy_code: int, channel: str, current_week: int,
                 field: str, old_value, new_value) -> None:
    """Append one audit entry. old_value may be None (no prior override)."""
    from datetime import datetime as _dt
    with _conn() as conn:
        conn.execute(
            "INSERT INTO audit_log "
            "(timestamp, hierarchy_code, channel, current_week, field, old_value, new_value) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (_dt.now().isoformat(timespec="seconds"),
             hierarchy_code, channel, current_week, field,
             str(old_value) if old_value is not None else None,
             str(new_value)),
        )
        conn.commit()


def db_get_audit_log(limit: int = 100, hierarchy_code: int = None,
                     field: str = None) -> List[Dict]:
    """Return most-recent audit entries (newest first), with optional filters."""
    clauses = []
    params  = []
    if hierarchy_code is not None:
        clauses.append("hierarchy_code = ?")
        params.append(hierarchy_code)
    if field:
        clauses.append("field = ?")
        params.append(field)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)
    with _conn() as conn:
        rows = conn.execute(
            f"SELECT id, timestamp, hierarchy_code, channel, current_week, "
            f"field, old_value, new_value "
            f"FROM audit_log {where} ORDER BY id DESC LIMIT ?",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def db_get_setting(key: str, default=None):
    """Return a settings value or default if not set."""
    with _conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def db_set_setting(key: str, value: str) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )
        conn.commit()


def db_get_budget_overrides() -> Dict[str, float]:
    """Return all per-(hc,channel) budget overrides as {'{hc}_{channel}': amount}."""
    with _conn() as conn:
        rows = conn.execute("SELECT key, value FROM settings WHERE key LIKE 'budget_%'").fetchall()
    return {r["key"][len("budget_"):]: float(r["value"]) for r in rows}


def db_delete_new_sku(hierarchy_code: int) -> bool:
    """Delete a new SKU by hierarchy_code. Returns True if a row was deleted."""
    with _conn() as conn:
        cur = conn.execute("DELETE FROM new_skus WHERE hierarchy_code = ?", (hierarchy_code,))
        conn.commit()
    return cur.rowcount > 0
