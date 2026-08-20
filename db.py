"""
db.py
AWS PostgreSQL connection pooling + every read/write helper the app needs.
This is the Python/Postgres port of global.R's "Entry database" and
"Master location helpers" sections, plus a new `users` table replacing
shinymanager's SQLite credentials store.

Column names passed to sql.Identifier() below always come from our own fixed
metadata (meta.ALL_ENTRY_FIELD_COLS) or hardcoded literals - never from raw
user input - so building queries with sql.Identifier is safe here.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timezone

import bcrypt
import pandas as pd
import psycopg2
import psycopg2.extras
import psycopg2.pool
from psycopg2 import sql
from psycopg2.extras import RealDictCursor

try:
    import streamlit as st
    _HAS_ST = True
except ImportError:  # allow scripts/*.py to import this module outside Streamlit
    _HAS_ST = False

_POOL = None


def _pg_config():
    if _HAS_ST:
        try:
            if "postgres" in st.secrets:
                cfg = st.secrets["postgres"]
                return dict(
                    host=cfg["host"],
                    port=cfg.get("port", 5432),
                    dbname=cfg["dbname"],
                    user=cfg["user"],
                    password=cfg["password"],
                    sslmode=cfg.get("sslmode", "require"),
                )
        except Exception:  # noqa: BLE001 - no secrets.toml found, fall through to env vars
            pass
    # fallback for standalone scripts (init_db.py / migrate_db.py) run via env vars
    return dict(
        host=os.environ["PGHOST"],
        port=os.environ.get("PGPORT", 5432),
        dbname=os.environ["PGDATABASE"],
        user=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"],
        sslmode=os.environ.get("PGSSLMODE", "require"),
    )


def _build_pool():
    cfg = _pg_config()
    return psycopg2.pool.SimpleConnectionPool(1, 10, **cfg)


def get_pool():
    global _POOL
    if _HAS_ST:
        cached = st.cache_resource(_build_pool)
        return cached()
    if _POOL is None:
        _POOL = _build_pool()
    return _POOL


@contextmanager
def get_conn():
    p = get_pool()
    conn = p.getconn()
    try:
        yield conn
    finally:
        p.putconn(conn)


# ---------------------------------------------------------------------------
# Master locations
# ---------------------------------------------------------------------------
def get_master_locations() -> pd.DataFrame:
    with get_conn() as conn:
        return pd.read_sql("SELECT state, district, block FROM master_locations", conn)


def replace_master_locations(df: pd.DataFrame):
    df = df.rename(columns=str.lower)[["state", "district", "block"]].copy()
    for c in ["state", "district", "block"]:
        df[c] = df[c].astype(str).str.strip()
    df = df.drop_duplicates()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM master_locations")
            rows = list(df.itertuples(index=False, name=None))
            if rows:
                psycopg2.extras.execute_values(
                    cur, "INSERT INTO master_locations (state, district, block) VALUES %s", rows
                )
        conn.commit()


# ---------------------------------------------------------------------------
# Entries (the captured data, one row per block)
# ---------------------------------------------------------------------------
def load_entry(state: str, district: str, block: str):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM entries WHERE state=%s AND district=%s AND block=%s",
                (state, district, block),
            )
            row = cur.fetchone()
    return dict(row) if row else None


def upsert_entry_fields(state: str, district: str, block: str, values: dict,
                         status: str | None = None, submitted_by: str | None = None):
    """Partial upsert: only columns present in `values` (+ status/submitted_by
    if given) are written; every other column already stored for this block
    is left untouched. Mirrors upsert_entry_fields() in global.R exactly -
    this is what lets field-staff saves and admin backend pushes coexist
    without clobbering each other."""
    set_cols = dict(values)
    if status is not None:
        set_cols["status"] = status
    if submitted_by is not None:
        set_cols["submitted_by"] = submitted_by
    set_cols["updated_at"] = datetime.now(timezone.utc)

    cols = ["state", "district", "block"] + list(set_cols.keys())
    vals = [state, district, block] + list(set_cols.values())

    insert_cols = sql.SQL(", ").join(sql.Identifier(c) for c in cols)
    insert_vals = sql.SQL(", ").join(sql.Placeholder() for _ in cols)
    update_set = sql.SQL(", ").join(
        sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(c), sql.Identifier(c))
        for c in set_cols.keys()
    )
    query = sql.SQL(
        "INSERT INTO entries ({cols}) VALUES ({vals}) "
        "ON CONFLICT (state, district, block) DO UPDATE SET {update_set}"
    ).format(cols=insert_cols, vals=insert_vals, update_set=update_set)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, vals)
        conn.commit()


def save_entry(state, district, block, values, status, submitted_by):
    """Field-staff Save as Draft / Submit Final."""
    upsert_entry_fields(state, district, block, values, status=status, submitted_by=submitted_by)


def save_backend_values(state, district, block, values, pushed_by):
    """Admin backend-data push. Deliberately does NOT touch `status`; tags
    submitted_by with '[backend] ' so the drill-down table can distinguish
    the source, matching the R app's documented behaviour/limitation."""
    upsert_entry_fields(state, district, block, values, status=None, submitted_by=f"[backend] {pushed_by}")


def get_all_entries() -> pd.DataFrame:
    with get_conn() as conn:
        return pd.read_sql("SELECT * FROM entries", conn)


def get_progress_summary():
    master = get_master_locations()
    entries = get_all_entries()

    if master.empty:
        return {"by_state": pd.DataFrame(), "overall": None, "master": master, "entries": entries}

    if entries.empty:
        entries = pd.DataFrame(columns=["state", "district", "block", "status", "updated_at"])

    joined = master.merge(
        entries[["state", "district", "block", "status", "updated_at"]],
        on=["state", "district", "block"], how="left",
    )

    by_state = (
        joined.groupby("state", as_index=False)
        .agg(
            total_blocks=("block", "count"),
            submitted=("status", lambda s: (s == "Submitted").sum()),
            draft=("status", lambda s: (s == "Draft").sum()),
        )
    )
    by_state["not_started"] = by_state["total_blocks"] - by_state["submitted"] - by_state["draft"]
    by_state["pct_submitted"] = (100 * by_state["submitted"] / by_state["total_blocks"]).round(1)
    by_state["pct_any_entry"] = (
        100 * (by_state["submitted"] + by_state["draft"]) / by_state["total_blocks"]
    ).round(1)
    last_updated = (
        joined.dropna(subset=["updated_at"]).groupby("state")["updated_at"].max()
        if joined["updated_at"].notna().any() else pd.Series(dtype=object)
    )
    by_state["last_updated"] = by_state["state"].map(last_updated)

    overall = dict(
        total_blocks=int(len(master)),
        submitted=int((joined["status"] == "Submitted").sum()),
        draft=int((joined["status"] == "Draft").sum()),
    )
    overall["not_started"] = overall["total_blocks"] - overall["submitted"] - overall["draft"]
    overall["pct_submitted"] = (
        round(100 * overall["submitted"] / overall["total_blocks"], 1) if overall["total_blocks"] else 0
    )

    return {"by_state": by_state, "overall": overall, "master": master, "entries": entries}


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def get_user(username: str):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE username=%s", (username,))
            row = cur.fetchone()
    return dict(row) if row else None


def verify_login(username: str, password: str):
    user = get_user(username)
    if not user or not user["active"]:
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    return user


def list_users() -> pd.DataFrame:
    with get_conn() as conn:
        return pd.read_sql(
            "SELECT username, is_master_admin, scope_type, state, district, block, "
            "dashboard_access, active, created_at, updated_at FROM users ORDER BY "
            "is_master_admin DESC, scope_type, state, district, block, username",
            conn,
        )


def upsert_user(username, password_plain, is_master_admin, scope_type, state, district, block,
                 dashboard_access=False, active=True):
    query = """
        INSERT INTO users (username, password_hash, is_master_admin, scope_type,
                            state, district, block, dashboard_access, active, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now())
        ON CONFLICT (username) DO UPDATE SET
            password_hash = EXCLUDED.password_hash,
            is_master_admin = EXCLUDED.is_master_admin,
            scope_type = EXCLUDED.scope_type,
            state = EXCLUDED.state,
            district = EXCLUDED.district,
            block = EXCLUDED.block,
            dashboard_access = EXCLUDED.dashboard_access,
            active = EXCLUDED.active,
            updated_at = now()
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (
                username, hash_password(password_plain), is_master_admin, scope_type,
                state, district, block, dashboard_access, active,
            ))
        conn.commit()


def bulk_upsert_users(df: pd.DataFrame):
    """Unified CSV: Username, Password, State, District, Block, DashboardAccess.
    District blank -> state scope; Block blank (District filled) -> district
    scope; all three filled -> block scope."""
    n_ok, errors = 0, []
    for i, row in df.iterrows():
        username = str(row.get("Username", "")).strip()
        password = str(row.get("Password", "")).strip()
        state = str(row.get("State", "")).strip()
        district = str(row.get("District", "")).strip()
        block = str(row.get("Block", "")).strip()
        dash = str(row.get("DashboardAccess", "")).strip().upper() in ("TRUE", "1", "YES")

        if not username or not password or not state:
            errors.append(f"Row {i + 2}: Username, Password and State are required - skipped.")
            continue

        if not district:
            scope_type, district, block = "state", None, None
        elif not block:
            scope_type, block = "district", None
        else:
            scope_type = "block"

        try:
            upsert_user(username, password, False, scope_type, state, district, block,
                        dashboard_access=dash, active=True)
            n_ok += 1
        except Exception as e:  # noqa: BLE001
            errors.append(f"Row {i + 2} ({username}): {e}")
    return n_ok, errors


def set_dashboard_access(username: str, value: bool):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET dashboard_access=%s, updated_at=now() WHERE username=%s",
                (value, username),
            )
        conn.commit()


def set_active(username: str, value: bool):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET active=%s, updated_at=now() WHERE username=%s",
                (value, username),
            )
        conn.commit()


def reset_password(username: str, new_password: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET password_hash=%s, updated_at=now() WHERE username=%s",
                (hash_password(new_password), username),
            )
        conn.commit()
