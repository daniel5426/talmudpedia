from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.workos_events import WorkOSWebhookEvent
from app.db.postgres.session import get_db
from app.services.workos_auth_service import WorkOSAuthService

router = APIRouter(prefix="/webhooks/workos", tags=["workos-webhooks"])


def _extract_event_fields(payload: dict[str, Any]) -> tuple[str | None, str | None, str | None, str | None]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    event_id = payload.get("id") or payload.get("event_id")
    event_type = payload.get("event") or payload.get("type")
    organization_id = (
        payload.get("organization_id")
        or data.get("organization_id")
        or data.get("organization")
        or payload.get("organization")
    )
    user_id = payload.get("user_id") or data.get("user_id") or data.get("user") or payload.get("user")
    return (
        str(event_id) if event_id else None,
        str(event_type) if event_type else None,
        str(organization_id) if organization_id else None,
        str(user_id) if user_id else None,
    )


@router.post("")
async def receive_workos_webhook(
    request: Request,
    sig_header: str | None = Header(None, alias="workos-signature"),
    db: AsyncSession = Depends(get_db),
):
    if not sig_header:
        raise HTTPException(status_code=401, detail="Missing WorkOS signature header")

    body = await request.body()
    service = WorkOSAuthService(db)
    service.verify_webhook_signature(payload=body, sig_header=sig_header)

    payload = json.loads(body.decode("utf-8"))
    workos_event_id, event_type, organization_id, user_id = _extract_event_fields(payload)
    if not workos_event_id or not event_type:
        raise HTTPException(status_code=400, detail="Invalid WorkOS webhook payload")

    existing = (
        await db.execute(
            select(WorkOSWebhookEvent).where(WorkOSWebhookEvent.workos_event_id == workos_event_id).limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return {"status": "duplicate"}

    record = WorkOSWebhookEvent(
        workos_event_id=workos_event_id,
        event_type=event_type,
        organization_id=organization_id,
        user_id=user_id,
        status="processed",
        payload=payload,
        processed_at=datetime.now(timezone.utc),
    )
    db.add(record)
    try:
        if event_type in {"user.created", "user.updated"} and user_id:
            await service.sync_workos_user_by_id(user_id)
        elif event_type in {"organization.created", "organization.updated"} and organization_id:
            await service.sync_workos_organization_by_id(
                workos_organization_id=organization_id,
                create_if_missing=False,
            )
        elif event_type in {"organization_membership.deleted", "dsync.user.deleted"} and user_id and organization_id:
            await service.remove_workos_membership(
                workos_user_id=user_id,
                workos_organization_id=organization_id,
            )
        elif event_type in {
            "organization_membership.created",
            "organization_membership.updated",
            "dsync.user.created",
            "dsync.user.updated",
        } and user_id and organization_id:
            await service.sync_workos_membership(
                workos_user_id=user_id,
                workos_organization_id=organization_id,
                create_org_if_missing=True,
            )
        record.status = "processed"
        record.processed_at = datetime.now(timezone.utc)
        await db.commit()
    except Exception as exc:
        record.status = "failed"
        record.error = str(exc)
        record.processed_at = datetime.now(timezone.utc)
        await db.commit()
        raise
    return {"status": "ok"}
