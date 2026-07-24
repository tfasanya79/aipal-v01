from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AuditLog


def _json_safe(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value


async def record_audit(
    db: AsyncSession,
    user_id: UUID,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    details: dict | list | None = None,
) -> AuditLog:
    row = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=_json_safe(details),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row
