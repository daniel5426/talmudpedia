from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Dict, Optional

from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent.core.state import AgentState


class BaseAgent(ABC):
    """
    Abstract base class for Agents.
    Wraps a LangGraph workflow.
    """

    def __init__(self):
        self.graph: Optional[CompiledStateGraph] = None

    @abstractmethod
    def build_graph(self) -> StateGraph:
        """Build and return the StateGraph for this agent."""
        pass

    def compile(self):
        """Compile the graph."""
        workflow = self.build_graph()
        self.graph = workflow.compile()

    async def astream_events(
        self,
        inputs: Dict[str, Any],
        config: Optional[Dict[str, Any]] = None,
        version: str = "v2",
        **kwargs: Any
    ) -> AsyncGenerator[Any, None]:
        """Stream events from the graph."""
        if not self.graph:
            self.compile()
        
        if not self.graph:
             raise ValueError("Graph failed to compile")

        async for event in self.graph.astream_events(inputs, config=config, version=version, **kwargs):
            yield event

    async def ainvoke(
        self,
        inputs: Dict[str, Any],
        config: Optional[Dict[str, Any]] = None,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """Invoke the graph."""
        if not self.graph:
            self.compile()
            
        if not self.graph:
             raise ValueError("Graph failed to compile")

        return await self.graph.ainvoke(inputs, config=config, **kwargs)
