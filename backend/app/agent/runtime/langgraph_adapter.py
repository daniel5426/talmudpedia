import asyncio
import logging
from typing import Any, AsyncGenerator, Dict, Optional

from langgraph.graph import END, StateGraph
from langgraph.types import Command

from app.agent.core.state import AgentState
from app.agent.execution.emitter import EventEmitter, active_emitter
from app.agent.execution.types import ExecutionEvent
from app.agent.graph.ir import GraphIR, RoutingMap
from app.agent.graph.node_factory import build_node_fn
from app.agent.runtime.base import RuntimeAdapter, RuntimeExecutable, RuntimeState

logger = logging.getLogger(__name__)


class LangGraphAdapter(RuntimeAdapter):
    name = "langgraph"

    async def compile(self, graph_ir: GraphIR, **kwargs) -> RuntimeExecutable:
        from app.agent.executors.standard import register_standard_operators
        register_standard_operators()
        checkpointer = kwargs.get("checkpointer")

        workflow = StateGraph(AgentState)

        for node in graph_ir.nodes:
            node_fn = build_node_fn(node, tenant_id=self.tenant_id, db=self.db)
            workflow.add_node(node.id, node_fn)

        conditional_nodes = set(graph_ir.routing_maps.keys())

        # Add static edges (non-conditional sources)
        for edge in graph_ir.edges:
            if edge.source in conditional_nodes:
                continue
            workflow.add_edge(edge.source, edge.target)

        # Add conditional edges
        for node_id, routing in graph_ir.routing_maps.items():
            path_map = routing.edges or {}
            if not path_map:
                continue

            def _router(state: Dict[str, Any], _path_map=path_map, _default=routing.default_handle):
                next_val = state.get("next")
                if next_val in _path_map:
                    return next_val
                if _default and _default in _path_map:
                    return _default
                return next_val

            workflow.add_conditional_edges(node_id, _router, path_map)

        if graph_ir.entry_point:
            workflow.set_entry_point(graph_ir.entry_point)

        for node_id in graph_ir.exit_nodes:
            workflow.add_edge(node_id, END)

        compiled = workflow.compile(
            checkpointer=checkpointer,
            interrupt_before=graph_ir.interrupt_before or None,
        )

        return RuntimeExecutable(graph_ir=graph_ir, workflow=workflow, compiled=compiled)

    async def run(
        self,
        executable: RuntimeExecutable,
        input_data: Dict[str, Any],
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        runtime_config = self._build_config(config)
        input_val = self._prepare_input(input_data, config)
        return await executable.compiled.ainvoke(input_val, config=runtime_config)

    async def stream(
        self,
        executable: RuntimeExecutable,
        input_data: Dict[str, Any],
        config: Dict[str, Any],
    ) -> AsyncGenerator[ExecutionEvent, None]:
        event_queue: asyncio.Queue[ExecutionEvent] = asyncio.Queue(maxsize=1000)
        emitter = EventEmitter(event_queue, config.get("run_id", "unknown"), config.get("mode", "debug"))
        token = active_emitter.set(emitter)

        runtime_config = self._build_config(config, emitter=emitter)
        input_val = self._prepare_input(input_data, config)

        execution_done = asyncio.Event()
        execution_error: Optional[Exception] = None

        async def run_graph():
            nonlocal execution_error
            try:
                async for _ in executable.compiled.astream_events(input_val, config=runtime_config, version="v2"):
                    # We deliberately ignore runtime-native events here.
                    # Platform events are emitted via EventEmitter.
                    pass
            except Exception as e:
                execution_error = e
            finally:
                execution_done.set()

        graph_task = asyncio.create_task(run_graph())

        try:
            while True:
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=0.1)
                    yield event
                except asyncio.TimeoutError:
                    if execution_done.is_set() and event_queue.empty():
                        break
        finally:
            await graph_task
            active_emitter.reset(token)
            if execution_error:
                raise execution_error

    def get_state(self, executable: RuntimeExecutable, config: Dict[str, Any]) -> RuntimeState:
        runtime_config = self._build_config(config)
        snapshot = executable.compiled.get_state(runtime_config)
        return RuntimeState(next=snapshot.next, values=snapshot.values)

    def _prepare_input(self, input_data: Dict[str, Any], config: Dict[str, Any]) -> Any:
        resume_payload = config.get("resume_payload")
        if resume_payload:
            return Command(resume=resume_payload)
        return input_data

    def _build_config(self, config: Dict[str, Any], emitter: Optional[EventEmitter] = None) -> Dict[str, Any]:
        configurable = {
            "thread_id": config.get("thread_id"),
        }
        if emitter:
            configurable["emitter"] = emitter
        recursion_limit = config.get("recursion_limit", 250)
        return {
            "configurable": configurable,
            "recursion_limit": recursion_limit,
        }
