"""
scripts/init_db.py
Run ONCE against the AWS Postgres instance to create the schema, seed the
master location list, and bootstrap the single master-admin account. Safe to
re-run (idempotent: uses IF NOT EXISTS / ON CONFLICT throughout).

Usage (from the streamlit_app/ directory, with .streamlit/secrets.toml filled in):
    python scripts/init_db.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

import db  # noqa: E402
import meta  # noqa: E402


def create_tables():
    field_cols_sql = ",\n      ".join(f'"{c}" TEXT' for c in meta.ALL_ENTRY_FIELD_COLS)
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS master_locations (
                    state TEXT, district TEXT, block TEXT,
                    PRIMARY KEY (state, district, block)
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id               SERIAL PRIMARY KEY,
                    username         TEXT UNIQUE NOT NULL,
                    password_hash    TEXT NOT NULL,
                    is_master_admin  BOOLEAN NOT NULL DEFAULT FALSE,
                    scope_type       TEXT CHECK (scope_type IN ('state','district','block')),
                    state            TEXT,
                    district         TEXT,
                    block            TEXT,
                    dashboard_access BOOLEAN NOT NULL DEFAULT FALSE,
                    active           BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at       TIMESTAMPTZ DEFAULT now(),
                    updated_at       TIMESTAMPTZ DEFAULT now()
                )
            """)
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS entries (
                    state TEXT, district TEXT, block TEXT,
                    {field_cols_sql},
                    status TEXT DEFAULT 'Draft',
                    submitted_by TEXT,
                    updated_at TIMESTAMPTZ,
                    PRIMARY KEY (state, district, block)
                )
            """)
        conn.commit()
    print("Tables ready: master_locations, users, entries.")


def seed_master_locations():
    existing = db.get_master_locations()
    if not existing.empty:
        print(f"master_locations already has {len(existing)} rows - skipping seed.")
        return
    seed_df = pd.read_csv(meta.MASTER_LOCATIONS_SEED_CSV, dtype=str)
    db.replace_master_locations(seed_df)
    print(f"Seeded master_locations with {len(seed_df)} rows from {meta.MASTER_LOCATIONS_SEED_CSV}.")


def bootstrap_master_admin():
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM users WHERE is_master_admin = TRUE")
            n = cur.fetchone()[0]
    if n > 0:
        print(f"{n} master admin account(s) already exist - skipping bootstrap.")
        return
    try:
        boot = st.secrets["bootstrap"]
        username = boot["master_admin_username"]
        password = boot["master_admin_password"]
    except Exception as e:  # noqa: BLE001
        raise SystemExit(
            "No master admin exists yet and [bootstrap] section is missing from "
            "st.secrets. Add master_admin_username / master_admin_password to "
            ".streamlit/secrets.toml and re-run."
        ) from e
    db.upsert_user(username, password, True, None, None, None, None,
                    dashboard_access=False, active=True)
    print(f"Bootstrapped master admin account '{username}'. Change this password after first login.")


if __name__ == "__main__":
    create_tables()
    seed_master_locations()
    bootstrap_master_admin()
    print("init_db.py complete.")
