from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    ConnectedAccount,
    ConnectedItem,
    ConnectorAuditLog,
    ExternalCommitment,
)
from .audit_service import record_audit
from .privacy_crypto import encrypt_value


async def list_connected_accounts(db: AsyncSession, user_id: UUID) -> list[ConnectedAccount]:
    result = await db.execute(
        select(ConnectedAccount).where(ConnectedAccount.user_id == user_id).order_by(ConnectedAccount.created_at.desc())
    )
    return list(result.scalars().all())


async def get_connected_account(db: AsyncSession, user_id: UUID, account_id: UUID) -> ConnectedAccount | None:
    result = await db.execute(
        select(ConnectedAccount).where(ConnectedAccount.user_id == user_id, ConnectedAccount.id == account_id)
    )
    return result.scalar_one_or_none()


async def create_connected_account(db: AsyncSession, user_id: UUID, data: dict) -> ConnectedAccount:
    row = ConnectedAccount(
        user_id=user_id,
        provider=data["provider"],
        account_label=data["account_label"],
        scopes=data.get("scopes"),
        status=data.get("status") or "active",
        access_token_encrypted=encrypt_value(data.get("access_token")),
        refresh_token_encrypted=encrypt_value(data.get("refresh_token")),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    await record_audit(db, user_id, "connector.create_account", row.provider, str(row.id), {"account_label": row.account_label})
    return row


async def update_connected_account(db: AsyncSession, user_id: UUID, account_id: UUID, data: dict) -> ConnectedAccount | None:
    row = await get_connected_account(db, user_id, account_id)
    if row is None:
        return None
    for key in ("provider", "account_label", "scopes", "status"):
        if key in data and data[key] is not None:
            setattr(row, key, data[key])
    if "access_token" in data:
        row.access_token_encrypted = encrypt_value(data.get("access_token"))
    if "refresh_token" in data:
        row.refresh_token_encrypted = encrypt_value(data.get("refresh_token"))
    row.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(row)
    await record_audit(db, user_id, "connector.update_account", row.provider, str(row.id), {"status": row.status})
    return row


async def delete_connected_account(db: AsyncSession, user_id: UUID, account_id: UUID) -> bool:
    row = await get_connected_account(db, user_id, account_id)
    if row is None:
        return False
    await db.execute(delete(ConnectedItem).where(ConnectedItem.user_id == user_id, ConnectedItem.connected_account_id == account_id))
    await db.execute(delete(ExternalCommitment).where(ExternalCommitment.user_id == user_id, ExternalCommitment.source_item_id.in_(
        select(ConnectedItem.id).where(ConnectedItem.user_id == user_id, ConnectedItem.connected_account_id == account_id)
    )))
    await db.delete(row)
    await db.commit()
    await record_audit(db, user_id, "connector.delete_account", row.provider, str(row.id))
    return True


async def list_connected_items(db: AsyncSession, user_id: UUID, provider: str | None = None) -> list[ConnectedItem]:
    stmt = select(ConnectedItem).where(ConnectedItem.user_id == user_id).order_by(ConnectedItem.created_at.desc())
    if provider:
        stmt = stmt.where(ConnectedItem.provider == provider)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def import_connected_item(db: AsyncSession, user_id: UUID, data: dict) -> ConnectedItem:
    row = ConnectedItem(
        user_id=user_id,
        connected_account_id=data["connected_account_id"],
        provider=data["provider"],
        item_type=data["item_type"],
        external_id=data["external_id"],
        title=data["title"],
        content_summary=data.get("content_summary"),
        source_metadata=data.get("source_metadata"),
        occurred_at=data.get("occurred_at"),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    await record_audit(db, user_id, "connector.import_item", row.provider, str(row.id), {"item_type": row.item_type})
    return row


async def create_commitment_from_item(
    db: AsyncSession,
    user_id: UUID,
    item: ConnectedItem,
    commitment_type: str,
    title: str,
    due_at: datetime | None = None,
    confidence: float = 0.7,
) -> ExternalCommitment:
    commitment = ExternalCommitment(
        user_id=user_id,
        source_provider=item.provider,
        source_item_id=item.id,
        commitment_type=commitment_type,
        title=title,
        due_at=due_at,
        status="open",
        confidence=confidence,
    )
    db.add(commitment)
    await db.commit()
    await db.refresh(commitment)
    await record_audit(db, user_id, "connector.create_commitment", item.provider, str(commitment.id), {"title": title})
    return commitment


async def list_commitments(db: AsyncSession, user_id: UUID) -> list[ExternalCommitment]:
    result = await db.execute(
        select(ExternalCommitment).where(ExternalCommitment.user_id == user_id).order_by(ExternalCommitment.created_at.desc())
    )
    return list(result.scalars().all())


async def list_audit_logs(db: AsyncSession, user_id: UUID) -> list[ConnectorAuditLog]:
    result = await db.execute(
        select(ConnectorAuditLog).where(ConnectorAuditLog.user_id == user_id).order_by(ConnectorAuditLog.created_at.desc())
    )
    return list(result.scalars().all())


async def connected_data_summary(db: AsyncSession, user_id: UUID) -> dict[str, int]:
    items = await db.execute(select(func.count()).select_from(ConnectedItem).where(ConnectedItem.user_id == user_id))
    commitments = await db.execute(select(func.count()).select_from(ExternalCommitment).where(ExternalCommitment.user_id == user_id))
    accounts = await db.execute(select(func.count()).select_from(ConnectedAccount).where(ConnectedAccount.user_id == user_id))
    return {
        "accounts": int(accounts.scalar_one() or 0),
        "items": int(items.scalar_one() or 0),
        "commitments": int(commitments.scalar_one() or 0),
    }


async def memory_candidates_from_item(item: ConnectedItem) -> list[dict[str, object]]:
    content = item.content_summary or item.title
    return [
        {
            "type": "important_event" if item.item_type in {"email", "calendar"} else "fact",
            "life_area": "business" if item.provider in {"email", "calendar"} else None,
            "title": item.title,
            "content": content,
            "importance": 7 if item.item_type in {"email", "calendar"} else 4,
            "confidence": 0.8,
            "sensitive": False,
            "user_approved": True,
            "source_provider": item.provider,
            "source_item_id": item.id,
        }
    ]


async def delete_connected_data(db: AsyncSession, user_id: UUID, provider: str | None = None) -> dict[str, int]:
    item_stmt = delete(ConnectedItem).where(ConnectedItem.user_id == user_id)
    account_stmt = delete(ConnectedAccount).where(ConnectedAccount.user_id == user_id)
    commitment_stmt = delete(ExternalCommitment).where(ExternalCommitment.user_id == user_id)
    if provider:
        item_stmt = item_stmt.where(ConnectedItem.provider == provider)
        account_stmt = account_stmt.where(ConnectedAccount.provider == provider)
        commitment_stmt = commitment_stmt.where(ExternalCommitment.source_provider == provider)
    item_count = await db.execute(item_stmt)
    account_count = await db.execute(account_stmt)
    commitment_count = await db.execute(commitment_stmt)
    await db.commit()
    return {
        "items": item_count.rowcount or 0,
        "accounts": account_count.rowcount or 0,
        "commitments": commitment_count.rowcount or 0,
    }
