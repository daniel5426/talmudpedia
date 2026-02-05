from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Dict, Optional
from uuid import UUID

from app.agent.execution.types import ExecutionEvent
from app.agent.graph.ir import GraphIR


@dataclass
class RuntimeState:
    next: Optional[Any]
    values: Dict[str, Any]


@dataclass
class RuntimeExecutable:
    graph_ir: GraphIR
    workflow: Any
    compiled: Any


class RuntimeAdapter(ABC):
    name: str = "base"

    def __init__(self, tenant_id: Optional[UUID] = None, db: Any = None):
        self.tenant_id = tenant_id
        self.db = db

    @abstractmethod
    async def compile(self, graph_ir: GraphIR, **kwargs) -> RuntimeExecutable:
        raise NotImplementedError

    @abstractmethod
    async def run(
        self,
        executable: RuntimeExecutable,
        input_data: Dict[str, Any],
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def stream(
        self,
        executable: RuntimeExecutable,
        input_data: Dict[str, Any],
        config: Dict[str, Any],
    ) -> AsyncGenerator[ExecutionEvent, None]:
        raise NotImplementedError

    @abstractmethod
    def get_state(self, executable: RuntimeExecutable, config: Dict[str, Any]) -> RuntimeState:
        raise NotImplementedError
