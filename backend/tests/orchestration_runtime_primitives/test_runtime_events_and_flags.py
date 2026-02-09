import asyncio

import pytest

from app.agent.execution.emitter import EventEmitter
from app.agent.executors.orchestration import JoinNodeExecutor, SpawnRunNodeExecutor
from artifacts.builtin.platform_sdk import handler


def _drain_events(queue: asyncio.Queue):
    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    return events


@pytest.mark.asyncio
async def test_spawn_run_emits_spawn_decision_and_child_lifecycle(monkeypatch):
    async def fake_spawn_run(self, **kwargs):
        return {
            "spawned_run_ids": ["11111111-1111-1111-1111-111111111111"],
            "idempotent": False,
        }

    monkeypatch.setattr(
        "app.services.orchestration_kernel_service.OrchestrationKernelService.spawn_run",
        fake_spawn_run,
    )

    queue: asyncio.Queue = asyncio.Queue()
    emitter = EventEmitter(queue, run_id="run-1", mode="debug")
    executor = SpawnRunNodeExecutor(tenant_id=None, db=object())

    await executor.execute(
        state={},
        config={
            "target_agent_slug": "child-a",
            "scope_subset": ["agents.execute"],
            "mapped_input_payload": {"q": "hello"},
        },
        context={
            "run_id": "22222222-2222-2222-2222-222222222222",
            "node_id": "spawn_node",
            "tenant_id": "tenant-1",
            "emitter": emitter,
        },
    )

    names = [event.event for event in _drain_events(queue)]
    assert "orchestration.spawn_decision" in names
    assert "orchestration.child_lifecycle" in names


@pytest.mark.asyncio
async def test_spawn_run_policy_deny_emits_policy_event(monkeypatch):
    async def fake_spawn_run(self, **kwargs):
        raise PermissionError("deny")

    monkeypatch.setattr(
        "app.services.orchestration_kernel_service.OrchestrationKernelService.spawn_run",
        fake_spawn_run,
    )

    queue: asyncio.Queue = asyncio.Queue()
    emitter = EventEmitter(queue, run_id="run-2", mode="debug")
    executor = SpawnRunNodeExecutor(tenant_id=None, db=object())

    with pytest.raises(PermissionError):
        await executor.execute(
            state={},
            config={
                "target_agent_slug": "child-a",
                "scope_subset": ["agents.execute"],
            },
            context={
                "run_id": "22222222-2222-2222-2222-222222222223",
                "node_id": "spawn_node",
                "tenant_id": "tenant-1",
                "emitter": emitter,
            },
        )

    names = [event.event for event in _drain_events(queue)]
    assert "orchestration.policy_deny" in names


@pytest.mark.asyncio
async def test_join_emits_join_decision_and_cancellation_event(monkeypatch):
    async def fake_join(self, **kwargs):
        return {
            "group_id": "33333333-3333-3333-3333-333333333333",
            "status": "failed",
            "complete": True,
            "mode": "fail_fast",
            "success_count": 0,
            "failure_count": 2,
            "running_count": 0,
            "cancellation_propagated": {
                "count": 1,
                "run_ids": ["44444444-4444-4444-4444-444444444444"],
                "reason": "join_fail_fast",
            },
        }

    monkeypatch.setattr(
        "app.services.orchestration_kernel_service.OrchestrationKernelService.join",
        fake_join,
    )

    queue: asyncio.Queue = asyncio.Queue()
    emitter = EventEmitter(queue, run_id="run-3", mode="debug")
    executor = JoinNodeExecutor(tenant_id=None, db=object())

    await executor.execute(
        state={},
        config={"orchestration_group_id": "33333333-3333-3333-3333-333333333333", "mode": "fail_fast"},
        context={
            "run_id": "22222222-2222-2222-2222-222222222224",
            "node_id": "join_node",
            "tenant_id": "tenant-1",
            "emitter": emitter,
        },
    )

    names = [event.event for event in _drain_events(queue)]
    assert "orchestration.join_decision" in names
    assert "orchestration.cancellation_propagation" in names


@pytest.mark.asyncio
async def test_option_a_flag_blocks_graph_orchestration(monkeypatch):
    monkeypatch.setenv("ORCHESTRATION_OPTION_A_ENABLED", "0")

    queue: asyncio.Queue = asyncio.Queue()
    emitter = EventEmitter(queue, run_id="run-4", mode="debug")
    executor = SpawnRunNodeExecutor(tenant_id=None, db=object())

    with pytest.raises(PermissionError):
        await executor.execute(
            state={},
            config={"target_agent_slug": "child-a", "scope_subset": ["agents.execute"]},
            context={
                "run_id": "22222222-2222-2222-2222-222222222225",
                "node_id": "spawn_node",
                "tenant_id": "tenant-1",
                "emitter": emitter,
            },
        )

    names = [event.event for event in _drain_events(queue)]
    assert "orchestration.policy_deny" in names


@pytest.mark.asyncio
async def test_option_b_flag_blocks_runtime_primitives_in_platform_sdk(monkeypatch):
    monkeypatch.setenv("ORCHESTRATION_OPTION_B_ENABLED", "0")

    out = handler.execute(
        state={},
        config={},
        context={
            "inputs": {
                "action": "spawn_run",
                "tenant_id": "tenant-1",
                "caller_run_id": "run-1",
            }
        },
    )

    assert out["context"]["result"]["status"] == "feature_disabled"
    assert out["context"]["errors"][0]["error"] == "feature_disabled"
