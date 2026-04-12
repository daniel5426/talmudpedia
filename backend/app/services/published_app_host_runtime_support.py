from __future__ import annotations

import os
from typing import Any, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.embedded_agent_runtime_service import list_public_run_events
from app.services.model_accounting import usage_payload_from_run
from app.services.runtime_attachment_service import RuntimeAttachmentService
from app.services.thread_detail_service import (
    serialize_thread_paging,
    serialize_thread_summary,
    serialize_thread_tree,
)
from app.services.thread_service import ThreadService, ThreadSubtreeNode, ThreadTurnPage


def _serialize_run_usage(run: Any) -> dict[str, Any] | None:
    return usage_payload_from_run(run)


def _serialize_thread_summary(thread: Any) -> dict[str, Any]:
    return serialize_thread_summary(thread)


def _turn_final_output(turn: Any) -> Any:
    metadata = turn.metadata_ if isinstance(getattr(turn, "metadata_", None), dict) else {}
    return metadata.get("final_output")


def _serialize_thread_paging(page: ThreadTurnPage) -> dict[str, Any]:
    return serialize_thread_paging(page)


async def _serialize_public_turn(
    *,
    db: AsyncSession,
    turn: Any,
    run_events_loader=list_public_run_events,
) -> dict[str, Any]:
    metadata = dict(turn.metadata_ or {})
    return {
        "id": str(turn.id),
        "run_id": str(turn.run_id),
        "turn_index": int(turn.turn_index or 0),
        "status": turn.status.value if hasattr(turn.status, "value") else str(turn.status),
        "user_input_text": turn.user_input_text,
        "assistant_output_text": turn.assistant_output_text,
        "final_output": _turn_final_output(turn),
        "run_usage": _serialize_run_usage(getattr(turn, "run", None)),
        "created_at": turn.created_at,
        "completed_at": turn.completed_at,
        "metadata": metadata,
        "response_blocks": metadata.get("response_blocks") if isinstance(metadata.get("response_blocks"), list) else [],
        "attachments": [
            RuntimeAttachmentService.serialize_attachment(link.attachment)
            for link in sorted(turn.attachment_links or [], key=lambda item: str(item.id))
            if getattr(link, "attachment", None) is not None
        ],
        "run_events": await run_events_loader(db=db, run_id=turn.run_id),
    }


async def _serialize_thread_detail(
    *,
    db: AsyncSession,
    thread: Any,
    page: ThreadTurnPage | None = None,
    subthread_tree: ThreadSubtreeNode | None = None,
    run_events_loader=list_public_run_events,
) -> dict[str, Any]:
    turns = list(page.turns if page is not None else sorted(list(thread.turns or []), key=lambda item: int(item.turn_index or 0)))
    payload = {
        **_serialize_thread_summary(thread),
        "turns": [await _serialize_public_turn(db=db, turn=turn, run_events_loader=run_events_loader) for turn in turns],
        "paging": _serialize_thread_paging(
            page if page is not None else ThreadTurnPage(turns=turns, has_more=False, next_before_turn_index=None)
        ),
    }
    if subthread_tree is not None:
        payload["lineage"] = ThreadService.serialize_thread_lineage(thread)
        payload["subthread_tree"] = await serialize_thread_tree(
            subthread_tree,
            serialize_turn=lambda turn: _serialize_public_turn(db=db, turn=turn, run_events_loader=run_events_loader),
        )
    return payload


def _apps_base_domain() -> str:
    return os.getenv("APPS_BASE_DOMAIN", "apps.localhost").strip().lower()


def _host_without_port(host_header: str | None) -> str:
    return (host_header or "").split(":", 1)[0].strip().lower()


def _slug_from_host(host_header: str | None) -> Optional[str]:
    host = _host_without_port(host_header)
    base_domain = _apps_base_domain()
    suffix = f".{base_domain}"
    if not host or host == base_domain or not host.endswith(suffix):
        return None
    slug = host[: -len(suffix)].strip().lower()
    return slug or None


def _request_origin_from_base_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def _request_relative_url(path: str, query: str) -> str:
    return f"{path}?{query}" if query else path


def _normalize_return_to_for_host(base_url: str, raw: str | None) -> str:
    value = (raw or "").strip()
    if not value:
        return "/"
    if value.startswith("/"):
        return value
    try:
        parsed = urlparse(value)
        current = urlparse(base_url)
        if parsed.scheme in {"http", "https"} and parsed.netloc and parsed.netloc == current.netloc:
            path = parsed.path or "/"
            if parsed.query:
                path = f"{path}?{parsed.query}"
            if parsed.fragment:
                path = f"{path}#{parsed.fragment}"
            return path
    except Exception:
        pass
    return "/"


def _append_query(url: str, params: dict[str, str]) -> str:
    parsed = urlparse(url)
    current = dict(parse_qsl(parsed.query, keep_blank_values=True))
    current.update(params)
    updated = parsed._replace(query=urlencode(current))
    return urlunparse(updated)
