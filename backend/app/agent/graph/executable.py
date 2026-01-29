import logging
from typing import Any, AsyncGenerator, Dict, List, Optional, Union
from uuid import UUID

from .schema import AgentGraph, NodeType, EdgeType

logger = logging.getLogger(__name__)

class ExecutableAgent:
    """
    A compiled agent ready for execution.
    
    This class wraps the LangGraph state machine and provides a clean interface
    for running and streaming agent executions.
    """
    
    def __init__(self, graph_definition: AgentGraph, compiled_graph: Any, config: dict[str, Any], snapshot: Any = None, workflow: Any = None):
        self.graph_definition = graph_definition
        self.compiled_graph = compiled_graph
        self.workflow = workflow
        self.config = config
        self.snapshot = snapshot

    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Executes the agent and returns the final result."""
        logger.info("Executing agent...")
        return await self.compiled_graph.ainvoke(input_data)

    async def stream(self, input_data: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
        """Executes the agent and yields execution events/tokens."""
        logger.info("Streaming agent execution...")
        async for event in self.compiled_graph.astream_events(input_data, version="v2"):
            yield event
