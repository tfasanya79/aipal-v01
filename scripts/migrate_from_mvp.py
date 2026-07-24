#!/usr/bin/env python3
"""Migrate profiles and open reminders from v1 SQLite to v2 PostgreSQL."""

from __future__ import annotations

import argparse
import sqlite3
import uuid
from datetime import UTC, datetime

try:
    import psycopg2
except ImportError:
    psycopg2 = None  # type: ignore


def migrate(sqlite_path: str, pg_url: str, dry_run: bool = True) -> None:
    if psycopg2 is None:
        raise SystemExit("pip install psycopg2-binary")
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    profiles = conn.execute("SELECT * FROM profiles").fetchall()
    reminders = conn.execute("SELECT * FROM reminders WHERE status != 'done'").fetchall()
    print(f"Found {len(profiles)} profiles, {len(reminders)} open reminders")

    if dry_run:
        print("Dry run — no writes")
        return

    pg = psycopg2.connect(pg_url)
    cur = pg.cursor()
    for p in profiles:
        uid = str(uuid.uuid4())
        email = f"migrated-{p['user_id'][:8]}@aipal.local"
        cur.execute(
            """
            INSERT INTO users (id, email, display_name, wake_name, about_me, timezone, created_at)
            VALUES (%s, %s, %s, %s, %s, 'UTC', %s)
            ON CONFLICT (email) DO NOTHING
            """,
            (uid, email, p.get("display_name"), p.get("wake_name"), p.get("about_me"), datetime.now(UTC)),
        )
    for r in reminders:
        cur.execute(
            """
            INSERT INTO tasks (user_id, title, status, source, created_at)
            SELECT id, %s, 'planned', 'migration', %s FROM users LIMIT 1
            """,
            (r["title"], datetime.now(UTC)),
        )
    pg.commit()
    print("Migration complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite", default="/var/lib/aipal/app.db")
    parser.add_argument("--pg", default="postgresql://aipal:aipal_dev@localhost:5432/aipal")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    migrate(args.sqlite, args.pg, dry_run=not args.apply)
