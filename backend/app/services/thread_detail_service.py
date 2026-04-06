from __future__ import annotations

from typing import Any, Awaitable, Callable

from app.db.postgres.models.agent_threads import AgentThread, AgentThreadTurn
from app.services.thread_service import ThreadService, ThreadSubtreeNode, ThreadTurnPage


def serialize_thread_summary(thread: AgentThread) -> dict[str, Any]:
    loaded_agent = thread.__dict__.get("agent")
    return {
        "id": str(thread.id),
        "title": thread.title,
        "status": thread.status.value if hasattr(thread.status, "value") else str(thread.status),
        "surface": thread.surface.value if hasattr(thread.surface, "value") else str(thread.surface),
        "agent_id": str(thread.agent_id) if thread.agent_id else None,
        "agent_name": getattr(loaded_agent, "name", None),
        "last_run_id": str(thread.last_run_id) if thread.last_run_id else None,
        "created_at": thread.created_at,
        "updated_at": thread.updated_at,
        "last_activity_at": thread.last_activity_at,
        "external_user_id": thread.external_user_id,
        "external_session_id": thread.external_session_id,
    }


def serialize_thread_paging(page: ThreadTurnPage) -> dict[str, Any]:
    return {
        "has_more": bool(page.has_more),
        "next_before_turn_index": page.next_before_turn_index,
    }


async def serialize_thread_tree(
    node: ThreadSubtreeNode,
    *,
    serialize_turn: Callable[[AgentThreadTurn], Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    return {
        "thread": serialize_thread_summary(node.thread),
        "lineage": ThreadService.serialize_thread_lineage(node.thread),
        "turns": [await serialize_turn(turn) for turn in node.page.turns],
        "paging": serialize_thread_paging(node.page),
        "has_children": bool(node.has_children),
        "children": [await serialize_thread_tree(child, serialize_turn=serialize_turn) for child in node.children],
    }
