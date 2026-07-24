"""Backfill the Phase 5 semantic index before serving production traffic."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Support the documented direct invocation from apps/api without requiring an
# editable package install or a caller-supplied PYTHONPATH.
API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

async def main() -> None:
    from sqlalchemy import select

    from app.db import async_session
    from app.models import User
    from app.services.memory_manager import memory_manager

    async with async_session() as db:
        user_ids = list((await db.execute(select(User.id))).scalars().all())
    total = 0
    for user_id in user_ids:
        async with async_session() as db:
            count = await memory_manager.backfill_user(db, user_id)
            total += count
            print(f"indexed user={user_id} documents={count}")
    print(f"memory index backfill complete users={len(user_ids)} documents={total}")


if __name__ == "__main__":
    asyncio.run(main())
