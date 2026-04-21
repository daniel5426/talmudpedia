from __future__ import annotations

from typing import Any, Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.runtime_attachment_service import RuntimeAttachmentService
from app.services.thread_detail_service import (
    serialize_thread_paging,
    serialize_thread_summary,
    serialize_thread_tree,
)
from app.services.thread_service import ThreadService, ThreadSubtreeNode, ThreadTurnPage


def turns_to_messages(turns: list[Any]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for turn in sorted(turns, key=lambda item: int(item.turn_index or 0)):
        if turn.user_input_text:
            messages.append({"role": "user", "content": turn.user_input_text})
        if turn.assistant_output_text:
            messages.append({"role": "assistant", "content": turn.assistant_output_text})
    return messages


def turn_final_output(turn: Any) -> Any:
    metadata = turn.metadata_ if isinstance(getattr(turn, "metadata_", None), dict) else {}
    return metadata.get("final_output")


def serialize_turn_base(turn: Any, *, run_usage: dict[str, Any] | None = None) -> dict[str, Any]:
    metadata = dict(turn.metadata_ or {})
    return {
        "id": str(turn.id),
        "run_id": str(turn.run_id),
        "turn_index": int(turn.turn_index or 0),
        "status": turn.status.value if hasattr(turn.status, "value") else str(turn.status),
        "user_input_text": turn.user_input_text,
        "assistant_output_text": turn.assistant_output_text,
        "final_output": turn_final_output(turn),
        "run_usage": run_usage,
        "created_at": turn.created_at,
        "completed_at": turn.completed_at,
        "metadata": metadata,
        "response_blocks": metadata.get("response_blocks") if isinstance(metadata.get("response_blocks"), list) else [],
        "attachments": [
            RuntimeAttachmentService.serialize_attachment(link.attachment)
            for link in sorted(turn.attachment_links or [], key=lambda item: str(item.id))
            if getattr(link, "attachment", None) is not None
        ],
    }


async def serialize_thread_detail(
    *,
    db: AsyncSession,
    thread: Any,
    page: ThreadTurnPage | None = None,
    subthread_tree: ThreadSubtreeNode | None = None,
    serialize_turn: Callable[[Any], Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    turns = list(page.turns if page is not None else sorted(list(thread.turns or []), key=lambda item: int(item.turn_index or 0)))
    payload = {
        **serialize_thread_summary(thread),
        "turns": [await serialize_turn(turn) for turn in turns],
        "paging": serialize_thread_paging(
            page if page is not None else ThreadTurnPage(turns=turns, has_more=False, next_before_turn_index=None)
        ),
    }
    if subthread_tree is not None:
        payload["lineage"] = ThreadService.serialize_thread_lineage(thread)
        payload["subthread_tree"] = await serialize_thread_tree(
            subthread_tree,
            serialize_turn=serialize_turn,
        )
    return payload
