from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(slots=True)
class ConnectedItemPayload:
    connected_account_id: UUID
    provider: str
    item_type: str
    external_id: str
    title: str
    content_summary: str | None = None
    source_metadata: dict | list | None = None
    occurred_at: datetime | None = None
