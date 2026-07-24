from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..db import get_db
from ..models import User
from ..rate_limit import rate_limit_dependency
from ..schemas import ConnectedAccountCreate, ConnectedAccountResponse, ConnectedItemImport, ConnectedItemResponse, ExternalCommitmentResponse
from ..services.connectors_service import (
    connected_data_summary,
    create_connected_account,
    delete_connected_account,
    delete_connected_data,
    import_connected_item,
    list_audit_logs,
    list_commitments,
    list_connected_accounts,
    list_connected_items,
)
from ..services.brain_briefing_service import generate_connector_briefing

router = APIRouter(prefix="/connectors", tags=["connectors"], dependencies=[Depends(rate_limit_dependency("connectors", limit=40))])


def _account(row) -> ConnectedAccountResponse:
    return ConnectedAccountResponse(
        id=row.id,
        provider=row.provider,
        account_label=row.account_label,
        scopes=row.scopes,
        status=row.status,
        last_sync_at=row.last_sync_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _item(row) -> ConnectedItemResponse:
    return ConnectedItemResponse(
        id=row.id,
        provider=row.provider,
        item_type=row.item_type,
        external_id=row.external_id,
        title=row.title,
        content_summary=row.content_summary,
        source_metadata=row.source_metadata,
        occurred_at=row.occurred_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _commitment(row) -> ExternalCommitmentResponse:
    return ExternalCommitmentResponse(
        id=row.id,
        source_provider=row.source_provider,
        source_item_id=row.source_item_id,
        commitment_type=row.commitment_type,
        title=row.title,
        due_at=row.due_at,
        status=row.status,
        confidence=float(row.confidence),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/summary")
async def summary(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await connected_data_summary(db, user.id)


@router.get("/accounts", response_model=list[ConnectedAccountResponse])
async def accounts(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return [_account(row) for row in await list_connected_accounts(db, user.id)]


@router.post("/accounts", response_model=ConnectedAccountResponse)
async def add_account(body: ConnectedAccountCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return _account(await create_connected_account(db, user.id, body.model_dump()))


@router.delete("/accounts/{account_id}")
async def remove_account(account_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not await delete_connected_account(db, user.id, account_id):
        raise HTTPException(status_code=404, detail="Connected account not found")
    return {"ok": True}


@router.get("/items", response_model=list[ConnectedItemResponse])
async def items(provider: str | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return [_item(row) for row in await list_connected_items(db, user.id, provider=provider)]


@router.post("/items/import", response_model=ConnectedItemResponse)
async def import_item(body: ConnectedItemImport, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return _item(await import_connected_item(db, user.id, body.model_dump()))


@router.post("/email/sync")
async def email_sync(payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    item = await import_connected_item(db, user.id, payload)
    return {"item": _item(item)}


@router.get("/email/items", response_model=list[ConnectedItemResponse])
async def email_items(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return [_item(row) for row in await list_connected_items(db, user.id, provider="email")]


@router.get("/email/important", response_model=list[ConnectedItemResponse])
async def email_important(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return [_item(row) for row in await list_connected_items(db, user.id, provider="email")]


@router.post("/calendar/sync")
async def calendar_sync(payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    item = await import_connected_item(db, user.id, payload)
    return {"item": _item(item)}


@router.get("/calendar/commitments", response_model=list[ExternalCommitmentResponse])
async def calendar_commitments(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return [_commitment(row) for row in await list_commitments(db, user.id)]


@router.get("/calendar/followups")
async def calendar_followups(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return [_commitment(row) for row in await list_commitments(db, user.id)]


@router.post("/documents/import")
async def document_import(payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    item = await import_connected_item(db, user.id, payload)
    return {"item": _item(item)}


@router.get("/documents/items", response_model=list[ConnectedItemResponse])
async def document_items(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return [_item(row) for row in await list_connected_items(db, user.id, provider="documents")]


@router.post("/documents/{item_id}/summarize")
async def document_summarize(item_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    items = await list_connected_items(db, user.id, provider="documents")
    row = next((item for item in items if str(item.id) == str(item_id)), None)
    if row is None:
        raise HTTPException(status_code=404, detail="Item not found")
    briefing = await generate_connector_briefing(
        db,
        user,
        source_type="documents",
        items=[f"{row.title}: {row.content_summary or ''}".strip()],
        user_message=f"Summarize this document for me in a useful companion briefing: {row.title}",
    )
    return {"summary": briefing.get("message") or row.content_summary or row.title, "source": "brain"}


@router.post("/whatsapp/import-export")
async def whatsapp_import(payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    item = await import_connected_item(db, user.id, payload)
    return {"item": _item(item)}


@router.get("/whatsapp/items", response_model=list[ConnectedItemResponse])
async def whatsapp_items(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return [_item(row) for row in await list_connected_items(db, user.id, provider="whatsapp")]


@router.delete("/data")
async def delete_data(provider: str | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await delete_connected_data(db, user.id, provider=provider)


@router.get("/audit-logs")
async def audit_logs(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = await list_audit_logs(db, user.id)
    return [
        {"id": str(row.id), "provider": row.provider, "action": row.action, "metadata": row.metadata_json, "created_at": row.created_at}
        for row in rows
    ]
