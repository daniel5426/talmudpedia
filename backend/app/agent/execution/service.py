import logging
import asyncio
import traceback
import json
from uuid import UUID
from datetime import datetime
from typing import Dict, Any, Optional, AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.postgres.models.agents import Agent, AgentRun, AgentTrace, RunStatus
from app.agent.graph.compiler import AgentCompiler
from app.agent.graph.schema import AgentGraph
from app.agent.runtime.registry import RuntimeAdapterRegistry
from app.agent.runtime.base import RuntimeState
from app.agent.execution.types import ExecutionEvent, EventVisibility, ExecutionMode
from app.agent.execution.durable_checkpointer import DurableMemorySaver

logger = logging.getLogger(__name__)

class AgentExecutorService:
    _checkpointer = DurableMemorySaver()

    def __init__(self, db: Optional[AsyncSession] = None):
        self.db = db
        # Initial compiler for non-execution tasks if needed, 
        # but _execute will create its own local compiler.
        self.compiler = AgentCompiler(db=db) if db else None

    @staticmethod
    def _apply_run_scoped_model_override(
        graph_definition: dict[str, Any],
        resolved_model_id: str | None,
    ) -> dict[str, Any]:
        if not resolved_model_id:
            return graph_definition

        nodes = graph_definition.get("nodes")
        if not isinstance(nodes, list):
            return graph_definition

        patched_nodes: list[Any] = []
        for raw_node in nodes:
            if not isinstance(raw_node, dict):
                patched_nodes.append(raw_node)
                continue
            node = dict(raw_node)
            node_type = str(node.get("type") or "").strip().lower()
            config = node.get("config")
            if node_type in {"agent", "llm", "llm_call", "classify"} and isinstance(config, dict):
                config = dict(config)
                if "model_id" in config:
                    config["model_id"] = resolved_model_id
                node["config"] = config
            patched_nodes.append(node)

        patched = dict(graph_definition)
        patched["nodes"] = patched_nodes
        return patched

    async def start_run(
        self, 
        agent_id: UUID, 
        input_params: Dict[str, Any], 
        user_id: Optional[UUID] = None, 
        background: bool = True,
        mode: ExecutionMode = ExecutionMode.DEBUG,
        requested_scopes: Optional[list[str]] = None,
        root_run_id: Optional[UUID] = None,
        parent_run_id: Optional[UUID] = None,
        parent_node_id: Optional[str] = None,
        depth: int = 0,
        spawn_key: Optional[str] = None,
        orchestration_group_id: Optional[UUID] = None,
    ) -> UUID:
        """
        Starts a new agent execution run.
        If background is True, it triggers a background task and returns the ID.
        If background is False, it only creates the DB record.
        """
        agent = await self.db.get(Agent, agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        # Create Run record
        runtime_context = {}
        if isinstance(input_params, dict):
            runtime_context = dict(input_params.get("context") or {})

        delegation_grant_id = runtime_context.get("grant_id")
        workload_principal_id = runtime_context.get("principal_id")
        initiator_user_id = runtime_context.get("initiator_user_id")

        parsed_grant_id = None
        parsed_principal_id = None
        parsed_initiator_id = None
        try:
            parsed_grant_id = UUID(str(delegation_grant_id)) if delegation_grant_id else None
        except Exception:
            parsed_grant_id = None
        try:
            parsed_principal_id = UUID(str(workload_principal_id)) if workload_principal_id else None
        except Exception:
            parsed_principal_id = None
        try:
            parsed_initiator_id = UUID(str(initiator_user_id)) if initiator_user_id else None
        except Exception:
            parsed_initiator_id = None

        run = AgentRun(
            agent_id=agent_id,
            tenant_id=agent.tenant_id,
            user_id=user_id or parsed_initiator_id,
            initiator_user_id=user_id or parsed_initiator_id,
            workload_principal_id=parsed_principal_id,
            delegation_grant_id=parsed_grant_id,
            input_params=input_params,
            status=RunStatus.queued,
            root_run_id=root_run_id,
            parent_run_id=parent_run_id,
            parent_node_id=parent_node_id,
            depth=depth,
            spawn_key=spawn_key,
            orchestration_group_id=orchestration_group_id,
            started_at=None,
            completed_at=None
        )
        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run)

        # Root runs self-reference for efficient run-tree queries.
        if run.root_run_id is None:
            run.root_run_id = run.id
            await self.db.commit()
            await self.db.refresh(run)

        # Create delegation context for runs with an initiator user context.
        # This covers both direct user-initiated runs and workload-initiated runs
        # that propagate initiator_user_id in runtime context.
        effective_initiator_id = user_id or parsed_initiator_id
        if effective_initiator_id is not None and run.delegation_grant_id is None:
            from app.services.delegation_service import DelegationService
            delegation = DelegationService(self.db)
            principal, grant, _approval_required = await delegation.create_agent_run_grant(
                agent=agent,
                initiator_user_id=effective_initiator_id,
                run_id=run.id,
                requested_scopes=requested_scopes or ((input_params.get("context") or {}).get("requested_scopes")),
            )
            run.workload_principal_id = principal.id
            run.delegation_grant_id = grant.id
            run.initiator_user_id = effective_initiator_id
            await self.db.commit()

        # Trigger background execution if requested
        if background:
            asyncio.create_task(self._execute_with_new_session(run.id, mode=mode))
        
        return run.id

    async def _execute_with_new_session(self, run_id: UUID, resume_payload: Optional[Dict[str, Any]] = None, mode: ExecutionMode = ExecutionMode.DEBUG):
        """Wrapper to provide a fresh session for background execution."""
        from app.db.postgres.engine import sessionmaker as get_session
        async with get_session() as session:
            try:
                await self._execute(run_id, db=session, resume_payload=resume_payload, mode=mode)
            except Exception as e:
                logger.error(f"Background execution wrapper failed: {e}")

    async def resume_run(self, run_id: UUID, user_input: Dict[str, Any], background: bool = True) -> None:
        """
        Resumes a paused agent execution run with user input.
        """
        run = await self.db.get(AgentRun, run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")
        
        if run.status != RunStatus.paused:
            raise ValueError(f"Run {run_id} is not paused (status: {run.status})")
        
        # Set status back to running/queued to prevent double resume
        run.status = RunStatus.queued
        await self.db.commit()

        if background:
            asyncio.create_task(self._execute_with_new_session(run.id, resume_payload=user_input))

    async def _execute(self, run_id: UUID, db: AsyncSession, resume_payload: Optional[Dict[str, Any]] = None, mode: ExecutionMode = ExecutionMode.DEBUG):
        """
        Core execution logic. This runs the LangGraph workflow.
        """
        try:
            async for _ in self.run_and_stream(run_id, db, resume_payload, mode):
                pass
        except Exception as e:
            # Error handling is inside run_and_stream or wrapped there
            logger.error(f"Execution run {run_id} failed: {e}")

    async def run_and_stream(
        self, 
        run_id: UUID, 
        db: AsyncSession, 
        resume_payload: Optional[Dict[str, Any]] = None,
        mode: ExecutionMode = ExecutionMode.DEBUG
    ) -> AsyncGenerator[ExecutionEvent, None]:
        """
        Executes the agent and yields TAGGED ExecutionEvents.
        DB persistence is handled asynchronously (Fire-and-Forget).
        
        Architecture:
        - Creates an event queue for explicit emissions from node executors.
        - Sets active_emitter ContextVar for implicit access in nodes.
        - Runs LangGraph execution and queue consumption concurrently.
        - Normalizes ALL events (both LangGraph and explicit) to ExecutionEvent.
        """
        # 1. Fetch Run & Agent
        run = await db.get(AgentRun, run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")

        agent = await db.get(Agent, run.agent_id)
        if not agent:
            raise ValueError(f"Agent {run.agent_id} not found")

        # Self-heal legacy/incomplete runs: ensure delegation context exists
        # before node execution so artifact workloads can mint scoped tokens.
        if run.delegation_grant_id is None and (run.user_id is not None or run.initiator_user_id is not None):
            from app.services.delegation_service import DelegationService
            delegation = DelegationService(db)
            effective_initiator_id = run.initiator_user_id or run.user_id
            principal, grant, _approval_required = await delegation.create_agent_run_grant(
                agent=agent,
                initiator_user_id=effective_initiator_id,
                run_id=run.id,
            )
            run.workload_principal_id = principal.id
            run.delegation_grant_id = grant.id
            run.initiator_user_id = effective_initiator_id
            await db.commit()

        # Capture input params before commit to avoid async lazy-loads
        run_input_params = run.input_params

        # Propagate delegation context into runtime state for node executors.
        runtime_context = {}
        if isinstance(run_input_params, dict):
            runtime_context = dict(run_input_params.get("context") or {})
        if run.delegation_grant_id:
            runtime_context["grant_id"] = str(run.delegation_grant_id)
        if run.workload_principal_id:
            runtime_context["principal_id"] = str(run.workload_principal_id)
        if run.initiator_user_id:
            runtime_context["initiator_user_id"] = str(run.initiator_user_id)
        runtime_context["run_id"] = str(run.id)
        if run.root_run_id:
            runtime_context["root_run_id"] = str(run.root_run_id)
        if run.parent_run_id:
            runtime_context["parent_run_id"] = str(run.parent_run_id)
        if run.parent_node_id:
            runtime_context["parent_node_id"] = str(run.parent_node_id)
        runtime_context["depth"] = int(run.depth or 0)
        if run.spawn_key:
            runtime_context["spawn_key"] = run.spawn_key
        if run.orchestration_group_id:
            runtime_context["orchestration_group_id"] = str(run.orchestration_group_id)
        if run.tenant_id:
            runtime_context["tenant_id"] = str(run.tenant_id)
        if run.resolved_model_id:
            runtime_context["resolved_model_id"] = str(run.resolved_model_id)
        runtime_context["orchestration_surface"] = "option_a_graphspec_v2"
        if isinstance(run_input_params, dict):
            run_input_params = dict(run_input_params)
            run_input_params["context"] = runtime_context
            # Keep auth/runtime context in persistent state bag too.
            # Top-level `context` is used by workflow logic and may be overwritten.
            existing_state = run_input_params.get("state")
            if not isinstance(existing_state, dict):
                existing_state = {}
            existing_state = dict(existing_state)
            existing_state["context"] = dict(runtime_context)
            run_input_params["state"] = existing_state
        else:
            run_input_params = {
                "context": runtime_context,
                "state": {"context": dict(runtime_context)},
            }

        # Update status
        run.status = RunStatus.running
        if not run.started_at:
            run.started_at = datetime.utcnow()
        await db.commit()

        # 2. Compile Graph to GraphIR
        compiler = AgentCompiler(db=db, tenant_id=agent.tenant_id)
        resolved_model_id = str(run.resolved_model_id) if run.resolved_model_id else None
        if not resolved_model_id:
            candidate = runtime_context.get("resolved_model_id")
            if candidate:
                resolved_model_id = str(candidate)
        graph_payload = agent.graph_definition if isinstance(agent.graph_definition, dict) else {}
        graph_payload = self._apply_run_scoped_model_override(graph_payload, resolved_model_id)
        graph_def = AgentGraph(**graph_payload)
        compile_input_params = run_input_params
        if resume_payload and isinstance(resume_payload, dict):
            if "approval" in resume_payload:
                compile_input_params = dict(run_input_params or {})
                compile_input_params["approval"] = resume_payload.get("approval")
        graph_ir = await compiler.compile(
            agent.id,
            agent.version,
            graph_def,
            config={"mode": mode.value},
            input_params=compile_input_params,
        )

        # 3. Create Runtime Adapter + Executable
        adapter_cls = RuntimeAdapterRegistry.get_default()
        adapter = adapter_cls(tenant_id=agent.tenant_id, db=db)
        executable = await adapter.compile(graph_ir, checkpointer=self._checkpointer)

        # 4. Prepare Config
        config = {
            "thread_id": str(run_id),
            "run_id": str(run_id),
            "mode": mode.value,
            "resume_payload": resume_payload,
            "grant_id": str(run.delegation_grant_id) if run.delegation_grant_id else None,
            "principal_id": str(run.workload_principal_id) if run.workload_principal_id else None,
            "initiator_user_id": str(run.initiator_user_id) if run.initiator_user_id else None,
            "tenant_id": str(run.tenant_id) if run.tenant_id else None,
            "user_id": str(run.user_id) if run.user_id else None,
            "auth_token": runtime_context.get("token"),
            "root_run_id": str(run.root_run_id) if run.root_run_id else None,
            "parent_run_id": str(run.parent_run_id) if run.parent_run_id else None,
            "parent_node_id": run.parent_node_id,
            "depth": int(run.depth or 0),
            "spawn_key": run.spawn_key,
            "orchestration_group_id": str(run.orchestration_group_id) if run.orchestration_group_id else None,
            "orchestration_surface": runtime_context.get("orchestration_surface"),
        }

        try:
            # 5. Stream Execution Events (Platform-normalized)
            async for event in adapter.stream(executable, run_input_params, config):
                self._schedule_trace_persistence(run_id, {
                    "event": event.event,
                    "data": event.data,
                    "name": event.name,
                    "run_id": event.span_id,
                    "metadata": event.metadata,
                    "parent_ids": [],
                })
                yield event

            # 6. Post-Execution Check
            snapshot: RuntimeState = adapter.get_state(executable, config)

            final_status = RunStatus.completed
            if snapshot.next:
                final_status = RunStatus.paused
                run.status = RunStatus.paused
                run.checkpoint = self._serialize_state(snapshot.values)
            else:
                run.status = RunStatus.completed
                run.output_result = self._serialize_state(snapshot.values)
                run.completed_at = datetime.utcnow()
                run.usage_tokens = 0

            # Emit final status event
            next_nodes = []
            if snapshot.next:
                next_ids = snapshot.next if isinstance(snapshot.next, list) else [snapshot.next]
                node_index = {n.id: n for n in graph_def.nodes}
                for next_id in next_ids:
                    node = node_index.get(next_id)
                    if node:
                        next_nodes.append({
                            "id": next_id,
                            "type": node.type,
                            "name": node.config.get("label", next_id),
                        })
                    else:
                        next_nodes.append({"id": next_id})

            yield ExecutionEvent(
                event="run_status",
                data={
                    "status": final_status.value,
                    "next": snapshot.next,
                    "next_nodes": next_nodes or None,
                },
                run_id=str(run_id),
                visibility=EventVisibility.CLIENT_SAFE,
                metadata={"mode": mode.value}
            )

            await db.commit()

        except Exception as e:
            await db.rollback()
            logger.error(f"Streaming execution failed for run {run_id}: {e}")
            traceback.print_exc()

            # Emit error event
            yield ExecutionEvent(
                event="error",
                data={"error": str(e)},
                run_id=str(run_id),
                visibility=EventVisibility.CLIENT_SAFE
            )

            # Update error status in fresh session
            try:
                from app.db.postgres.engine import sessionmaker as get_session
                async with get_session() as err_db:
                    err_run = await err_db.get(AgentRun, run_id)
                    if err_run:
                        err_run.status = RunStatus.failed
                        err_run.error_message = str(e)
                        err_run.completed_at = datetime.utcnow()
                        await err_db.commit()
            except Exception as se:
                logger.error(f"Failed to save error status for {run_id}: {se}")

    def _schedule_trace_persistence(self, run_id: UUID, event: Dict[str, Any]):
        """
        Schedules trace persistence as a background background task.
        Fully decoupled from the execution loop.
        """
        asyncio.create_task(self._persist_trace_safe(run_id, event))

    async def _persist_trace_safe(self, run_id: UUID, event: Dict[str, Any]):
        """
        Safe wrapper for trace persistence that swallows errors.
        Creates its own DB session.
        """
        from app.db.postgres.engine import sessionmaker as get_session
        try:
            async with get_session() as session:
                await self._save_trace_event(run_id, session, event)
                await session.commit()
        except Exception as e:
            logger.error(f"Trace persistence failed [Run {run_id}]: {e}")
            # Do NOT re-raise

    async def _save_trace_event(self, run_id: UUID, db: AsyncSession, event: Dict[str, Any]):
        """
        Persists execution events to AgentTrace table.
        """
        from uuid import uuid4 as _uuid4
        kind = event.get("event")
        name = event.get("name")
        span_id = event.get("run_id")
        span_id_str = str(span_id) if span_id is not None else None
        
        if kind not in ("on_chain_start", "on_chain_end", "on_tool_start", "on_tool_end", "node_start", "node_end"):
            return
        if not span_id_str:
            return

        # Avoid duplicate inserts for the same span
        existing = await db.execute(
            select(AgentTrace).where(
                AgentTrace.run_id == run_id,
                AgentTrace.span_id == span_id_str,
            )
        )
        trace_existing = existing.scalars().first()

        if kind.endswith("_start"):
            if trace_existing:
                return
            trace = AgentTrace(
                id=_uuid4(),
                run_id=run_id,
                span_id=span_id_str,
                parent_span_id=str(event.get("parent_ids", [])[-1]) if event.get("parent_ids") else None,
                name=name,
                span_type=kind,
                inputs=self._serialize_state(event.get("data", {}).get("input")),
                start_time=datetime.utcnow(),
                metadata_=event.get("metadata", {})
            )
            db.add(trace)
        
        elif kind.endswith("_end"):
            if trace_existing:
                trace_existing.end_time = datetime.utcnow()
                trace_existing.outputs = self._serialize_state(event.get("data", {}).get("output"))
            else:
                trace = AgentTrace(
                    id=_uuid4(),
                    run_id=run_id,
                    span_id=span_id_str,
                    parent_span_id=str(event.get("parent_ids", [])[-1]) if event.get("parent_ids") else None,
                    name=name,
                    span_type=kind,
                    inputs=self._serialize_state(event.get("data", {}).get("input")),
                    start_time=datetime.utcnow(),
                    end_time=datetime.utcnow(),
                    outputs=self._serialize_state(event.get("data", {}).get("output")),
                    metadata_=event.get("metadata", {})
                )
                db.add(trace)

    def _serialize_state(self, state: Any) -> Any:
        """Helper to make state JSON serializable (handling LangChain messages)."""
        if isinstance(state, dict):
            return {k: self._serialize_state(v) for k, v in state.items()}
        if isinstance(state, list):
            return [self._serialize_state(v) for v in state]
        
        # Handle LangChain messages
        if hasattr(state, "type") and hasattr(state, "content") and not isinstance(state, dict):
            # This is likely a BaseMessage (HumanMessage, AIMessage, etc.)
            return {
                "role": getattr(state, "type"),
                "content": getattr(state, "content"),
                "additional_kwargs": getattr(state, "additional_kwargs", {}),
                "name": getattr(state, "name", None)
            }
        
        # Fallback for other non-serializable objects (like UUIDs)
        if isinstance(state, UUID):
            return str(state)
        if isinstance(state, datetime):
            return state.isoformat()
            
        return state
