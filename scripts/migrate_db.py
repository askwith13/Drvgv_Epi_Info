"""
scripts/migrate_db.py
Additive, non-destructive migration: adds any `entries` columns that are in
meta.ALL_ENTRY_FIELD_COLS but missing from the live table (e.g. after a new
field is added to field_metadata.csv post-launch). Never drops or renames
columns, never touches existing data. Mirrors the "migrate in any new
columns" branch of init_entry_db() in global.R.

Usage: python scripts/migrate_db.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db  # noqa: E402
import meta  # noqa: E402


def migrate():
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'entries'
            """)
            existing = {r[0] for r in cur.fetchall()}
            missing = [c for c in meta.ALL_ENTRY_FIELD_COLS if c not in existing]
            for col in missing:
                cur.execute(f'ALTER TABLE entries ADD COLUMN "{col}" TEXT')
                print(f"Added column: {col}")
        conn.commit()
    if not missing:
        print("No missing columns - entries table already up to date.")
    else:
        print(f"Migration complete - added {len(missing)} column(s).")


if __name__ == "__main__":
    migrate()
