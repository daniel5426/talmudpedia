import pytest

from app.agent.executors.base import BaseNodeExecutor
from app.agent.executors.standard import register_standard_operators
from app.agent.execution.emitter import active_emitter
from app.agent.graph.ir import GraphIR, GraphIRNode, GraphIREdge
from app.agent.graph.node_factory import build_node_fn
from app.agent.registry import AgentExecutorRegistry
from app.agent.runtime.base import RuntimeAdapter, RuntimeExecutable, RuntimeState
from app.agent.runtime.langgraph_adapter import LangGraphAdapter
from app.agent.runtime.registry import RuntimeAdapterRegistry


class DummyAdapter(RuntimeAdapter):
    name = "dummy"

    async def compile(self, graph_ir: GraphIR, **kwargs) -> RuntimeExecutable:
        return RuntimeExecutable(graph_ir=graph_ir, workflow=None, compiled=None)

    async def run(self, executable: RuntimeExecutable, input_data, config):
        return {"ok": True, "input": input_data}

    async def stream(self, executable: RuntimeExecutable, input_data, config):
        if False:
            yield None

    def get_state(self, executable: RuntimeExecutable, config):
        return RuntimeState(next=None, values={"ok": True})


class NoopExecutor(BaseNodeExecutor):
    async def execute(self, state, config, context=None):
        emitter = active_emitter.get()
        if emitter:
            node_id = context.get("node_id", "noop")
            emitter.emit_node_start(node_id, "Noop", "noop_test", {"input": "ping"})
            emitter.emit_node_end(node_id, "Noop", "noop_test", {"output": "pong"})
        return {}


@pytest.mark.asyncio
async def test_runtime_registry_default_and_custom():
    default_cls = RuntimeAdapterRegistry.get_default()
    assert default_cls is LangGraphAdapter

    RuntimeAdapterRegistry.register("dummy", DummyAdapter)
    RuntimeAdapterRegistry.set_default("dummy")
    try:
        assert RuntimeAdapterRegistry.get_default() is DummyAdapter
    finally:
        RuntimeAdapterRegistry.set_default("langgraph")


@pytest.mark.asyncio
async def test_langgraph_adapter_compile_run_and_stream():
    register_standard_operators()

    graph_ir = GraphIR(
        nodes=[
            GraphIRNode(id="start", type="start"),
            GraphIRNode(id="end", type="end", config={"output_message": "ok"}),
        ],
        edges=[GraphIREdge(id="e1", source="start", target="end")],
        entry_point="start",
        exit_nodes=["end"],
    )

    adapter = LangGraphAdapter()
    executable = await adapter.compile(graph_ir)

    result = await adapter.run(executable, {"messages": []}, config={})
    assert result.get("_node_outputs", {}).get("end", {}).get("final_output") == "ok"

    events = []
    async for event in adapter.stream(executable, {"messages": []}, config={"run_id": "run-1", "mode": "debug"}):
        events.append(event)
    assert events == []


@pytest.mark.asyncio
async def test_langgraph_adapter_stream_emits_platform_events():
    register_standard_operators()
    AgentExecutorRegistry.register("noop_test", NoopExecutor)

    graph_ir = GraphIR(
        nodes=[
            GraphIRNode(id="start", type="start"),
            GraphIRNode(id="noop", type="noop_test"),
            GraphIRNode(id="end", type="end"),
        ],
        edges=[
            GraphIREdge(id="e1", source="start", target="noop"),
            GraphIREdge(id="e2", source="noop", target="end"),
        ],
        entry_point="start",
        exit_nodes=["end"],
    )

    adapter = LangGraphAdapter()
    executable = await adapter.compile(graph_ir)

    events = []
    async for event in adapter.stream(executable, {"messages": []}, config={"run_id": "run-2", "mode": "debug"}):
        events.append(event.event)

    assert "node_start" in events
    assert "node_end" in events


@pytest.mark.asyncio
async def test_node_factory_missing_executor_returns_state():
    node_fn = build_node_fn(GraphIRNode(id="missing", type="not_registered"), tenant_id=None, db=None)
    result = await node_fn({"ok": True})
    assert result == {"ok": True}
