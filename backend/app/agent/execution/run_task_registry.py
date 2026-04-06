from __future__ import annotations

import asyncio
import threading
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable


@dataclass
class _RunRegistryEntry:
    root_run_id: str
    parent_run_id: str | None = None


_lock = threading.Lock()
_tasks_by_run: dict[str, set[asyncio.Task[object]]] = defaultdict(set)
_lineage_by_run: dict[str, _RunRegistryEntry] = {}
_cancel_requested_run_ids: set[str] = set()


def _normalize_run_id(run_id: object | None) -> str | None:
    if run_id in (None, ""):
        return None
    return str(run_id)


def record_run_lineage(
    run_id: object,
    *,
    root_run_id: object | None = None,
    parent_run_id: object | None = None,
) -> None:
    run_key = _normalize_run_id(run_id)
    if run_key is None:
        return
    root_key = _normalize_run_id(root_run_id) or run_key
    parent_key = _normalize_run_id(parent_run_id)
    with _lock:
        _lineage_by_run[run_key] = _RunRegistryEntry(root_run_id=root_key, parent_run_id=parent_key)


def register_run_task(
    run_id: object,
    task: asyncio.Task[object] | None = None,
    *,
    root_run_id: object | None = None,
    parent_run_id: object | None = None,
) -> None:
    current_task = task or asyncio.current_task()
    run_key = _normalize_run_id(run_id)
    if current_task is None or run_key is None:
        return
    with _lock:
        _tasks_by_run[run_key].add(current_task)
        existing = _lineage_by_run.get(run_key)
        _lineage_by_run[run_key] = _RunRegistryEntry(
            root_run_id=_normalize_run_id(root_run_id) or (existing.root_run_id if existing else run_key),
            parent_run_id=_normalize_run_id(parent_run_id) if parent_run_id is not None else (existing.parent_run_id if existing else None),
        )


def unregister_run_task(run_id: object, task: asyncio.Task[object] | None = None) -> None:
    current_task = task or asyncio.current_task()
    run_key = _normalize_run_id(run_id)
    if current_task is None or run_key is None:
        return
    with _lock:
        tasks = _tasks_by_run.get(run_key)
        if tasks:
            tasks.discard(current_task)
            if not tasks:
                _tasks_by_run.pop(run_key, None)


def mark_run_cancel_requested(run_ids: Iterable[object]) -> None:
    with _lock:
        for run_id in run_ids:
            run_key = _normalize_run_id(run_id)
            if run_key is not None:
                _cancel_requested_run_ids.add(run_key)


def clear_run_cancel_requested(run_id: object) -> None:
    run_key = _normalize_run_id(run_id)
    if run_key is None:
        return
    with _lock:
        _cancel_requested_run_ids.discard(run_key)


def is_run_cancel_requested(
    *,
    run_id: object | None = None,
    root_run_id: object | None = None,
    parent_run_id: object | None = None,
) -> bool:
    candidate_keys = {
        key
        for key in (
            _normalize_run_id(run_id),
            _normalize_run_id(root_run_id),
            _normalize_run_id(parent_run_id),
        )
        if key is not None
    }
    if not candidate_keys:
        return False

    with _lock:
        visited: set[str] = set()
        frontier = list(candidate_keys)
        while frontier:
            current = frontier.pop()
            if current in visited:
                continue
            visited.add(current)
            if current in _cancel_requested_run_ids:
                return True
            entry = _lineage_by_run.get(current)
            if entry is None:
                continue
            if entry.root_run_id not in visited:
                frontier.append(entry.root_run_id)
            if entry.parent_run_id and entry.parent_run_id not in visited:
                frontier.append(entry.parent_run_id)
    return False


def cancel_run_tasks(run_ids: Iterable[object]) -> int:
    current_task = asyncio.current_task()
    to_cancel: set[asyncio.Task[object]] = set()
    with _lock:
        for run_id in run_ids:
            run_key = _normalize_run_id(run_id)
            if run_key is None:
                continue
            _cancel_requested_run_ids.add(run_key)
            tasks = _tasks_by_run.get(run_key)
            if not tasks:
                continue
            stale = {task for task in tasks if task.done()}
            tasks.difference_update(stale)
            if not tasks:
                _tasks_by_run.pop(run_key, None)
                continue
            to_cancel.update(tasks)

    cancelled = 0
    for task in to_cancel:
        if task.done() or task is current_task:
            continue
        task.cancel()
        cancelled += 1
    return cancelled
