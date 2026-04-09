from __future__ import annotations

import asyncio

from app.workers.async_runner import run_async


def test_worker_async_runner_reuses_one_persistent_event_loop() -> None:
    async def _loop_id() -> int:
        return id(asyncio.get_running_loop())

    first = run_async(_loop_id())
    second = run_async(_loop_id())

    assert first == second
