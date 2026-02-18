from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncGenerator, Protocol

from app.db.postgres.models.agents import AgentRun
from app.db.postgres.models.published_apps import PublishedApp


@dataclass(frozen=True)
class EngineRunContext:
    app: PublishedApp
    run: AgentRun
    resume_payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class EngineStreamEvent:
    event: str
    stage: str
    payload: dict[str, Any] | None = None
    diagnostics: list[dict[str, Any]] | None = None


@dataclass(frozen=True)
class EngineCancelResult:
    confirmed: bool
    diagnostics: list[dict[str, Any]] | None = None


class PublishedAppCodingAgentEngine(Protocol):
    async def stream(self, ctx: EngineRunContext) -> AsyncGenerator[EngineStreamEvent, None]:
        ...

    async def cancel(self, run: AgentRun) -> EngineCancelResult:
        ...
