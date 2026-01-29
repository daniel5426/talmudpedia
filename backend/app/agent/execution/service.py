import logging
import asyncio
import traceback
import json
from uuid import UUID
from datetime import datetime
from typing import Dict, Any, Optional, AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from langgraph.types import Command
from langgraph.checkpoint.memory import MemorySaver

from app.db.postgres.models.agents import Agent, AgentRun, AgentTrace, RunStatus
from app.agent.graph.compiler import AgentCompiler, ExecutableAgent
from app.agent.graph.schema import AgentGraph
from app.agent.core.state import AgentState
from app.agent.execution.types import ExecutionEvent, EventVisibility, ExecutionMode

logger = logging.getLogger(__name__)

class AgentExecutorService:
    # Use a persistent checkpointer if possible. 
    # For now, we use a class-level MemorySaver to support cross-request state in memory.
    # In production, this would be a PostgresCheckpointSaver.
    _checkpointer = MemorySaver()

    def __init__(self, db: Optional[AsyncSession] = None):
        self.db = db
        # Initial compiler for non-execution tasks if needed, 
        # but _execute will create its own local compiler.
        self.compiler = AgentCompiler(db=db) if db else None

    async def start_run(
        self, 
        agent_id: UUID, 
        input_params: Dict[str, Any], 
        user_id: Optional[UUID] = None, 
        background: bool = True,
        mode: ExecutionMode = ExecutionMode.DEBUG
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
        run = AgentRun(
            agent_id=agent_id,
            tenant_id=agent.tenant_id,
            user_id=user_id,
            input_params=input_params,
            status=RunStatus.queued,
            started_at=None,
            completed_at=None
        )
        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run)

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
        from .emitter import EventEmitter, active_emitter
        
        # Event queue for explicit emissions (token, node_start, node_end)
        event_queue: asyncio.Queue[ExecutionEvent] = asyncio.Queue(maxsize=1000)
        emitter = EventEmitter(event_queue, str(run_id), mode.value)
        
        # Set context var for implicit propagation
        token = active_emitter.set(emitter)
        
        # Sentinel to signal execution completion
        execution_done = asyncio.Event()
        execution_error: Optional[Exception] = None
        
        async def run_graph():
            nonlocal execution_error
            try:
                # 1. Fetch Run & Agent
                run = await db.get(AgentRun, run_id)
                if not run:
                    raise ValueError(f"Run {run_id} not found")

                agent = await db.get(Agent, run.agent_id)
                if not agent:
                    raise ValueError(f"Agent {run.agent_id} not found")

                # Update status
                run.status = RunStatus.running
                if not run.started_at:
                    run.started_at = datetime.utcnow()
                await db.commit()

                # 2. Compile Graph
                compiler = AgentCompiler(db=db, tenant_id=agent.tenant_id)
                graph_def = AgentGraph(**agent.graph_definition)
                executable = await compiler.compile(agent.id, agent.version, graph_def)
                
                # 3. Setup Runtime & Checkpointer
                checkpointer = self._checkpointer
                interrupt_before_nodes = [n.id for n in graph_def.nodes if n.type == "human_input"]
                
                if not executable.workflow:
                     raise ValueError("ExecutableAgent missing workflow definition")

                workflow = executable.workflow.compile(
                    checkpointer=checkpointer,
                    interrupt_before=interrupt_before_nodes
                )
                
                # 4. Prepare Configuration - PASS EMITTER
                config = {"configurable": {"thread_id": str(run_id), "emitter": emitter}}

                # 5. Run Execution
                input_val = Command(resume=resume_payload) if resume_payload else run.input_params

                async for event in workflow.astream_events(input_val, config=config, version="v2"):
                    # Fire-and-forget trace persistence
                    self._schedule_trace_persistence(run_id, event.copy())
                    
                    # Normalize LangGraph event to ExecutionEvent
                    # We skip on_chat_model_stream since tokens are now explicit
                    kind = event.get("event")
                    if kind == "on_chat_model_stream":
                        # Skip - tokens are now emitted explicitly by LLMNodeExecutor
                        continue
                    
                    # Determine Visibility
                    visibility = EventVisibility.INTERNAL
                    if kind == "run_status":
                        visibility = EventVisibility.CLIENT_SAFE
                    
                    # Enqueue as ExecutionEvent
                    try:
                        event_queue.put_nowait(ExecutionEvent(
                            event=kind,
                            data=event.get("data", {}),
                            run_id=str(run_id),
                            span_id=event.get("run_id"),
                            name=event.get("name"),
                            visibility=visibility,
                            metadata={"mode": mode.value}
                        ))
                    except asyncio.QueueFull:
                        logger.warning(f"Event queue full, dropping LangGraph event: {kind}")

                # 6. Post-Execution Check
                snapshot = workflow.get_state(config)
                
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

                # Enqueue final status event
                try:
                    event_queue.put_nowait(ExecutionEvent(
                        event="run_status",
                        data={"status": final_status.value},
                        run_id=str(run_id),
                        visibility=EventVisibility.CLIENT_SAFE,
                        metadata={"mode": mode.value}
                    ))
                except asyncio.QueueFull:
                    pass

                await db.commit()
                
            except Exception as e:
                execution_error = e
                await db.rollback()
                logger.error(f"Streaming execution failed for run {run_id}: {e}")
                traceback.print_exc()
                
                # Emit error event
                try:
                    event_queue.put_nowait(ExecutionEvent(
                        event="error",
                        data={"error": str(e)},
                        run_id=str(run_id),
                        visibility=EventVisibility.CLIENT_SAFE
                    ))
                except asyncio.QueueFull:
                    pass
                
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
            finally:
                execution_done.set()
        
        # Start graph execution in background
        graph_task = asyncio.create_task(run_graph())
        
        # Yield events from queue until execution is done and queue is empty
        try:
            while True:
                try:
                    # Wait for event with timeout to check execution status
                    event = await asyncio.wait_for(event_queue.get(), timeout=0.1)
                    yield event
                except asyncio.TimeoutError:
                    # Check if execution is done and queue is empty
                    if execution_done.is_set() and event_queue.empty():
                        break
        finally:
            # Ensure graph task is awaited
            await graph_task

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
        kind = event.get("event")
        name = event.get("name")
        span_id = event.get("run_id")
        
        if kind not in ("on_chain_start", "on_chain_end", "on_tool_start", "on_tool_end", "on_chat_model_start", "on_chat_model_end"):
            return

        if kind.endswith("_start"):
            trace = AgentTrace(
                id=span_id,
                run_id=run_id,
                span_id=str(span_id),
                parent_span_id=str(event.get("parent_ids", [])[-1]) if event.get("parent_ids") else None,
                name=name,
                span_type=kind,
                inputs=self._serialize_state(event.get("data", {}).get("input")),
                start_time=datetime.utcnow(),
                metadata_=event.get("metadata", {})
            )
            db.add(trace)
        
        elif kind.endswith("_end"):
            # Check if exists first (it should)
            result = await db.execute(select(AgentTrace).where(AgentTrace.span_id == str(span_id)))
            trace = result.scalars().first()
            if trace:
                trace.end_time = datetime.utcnow()
                trace.outputs = self._serialize_state(event.get("data", {}).get("output"))

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

