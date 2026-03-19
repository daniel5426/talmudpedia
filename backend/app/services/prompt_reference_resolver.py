from __future__ import annotations

from copy import deepcopy
import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.db.postgres.models.agents import Agent
from app.db.postgres.models.artifact_runtime import Artifact, ArtifactRevision
from app.db.postgres.models.prompts import PromptLibrary, PromptStatus
from app.db.postgres.models.registry import ToolRegistry


PROMPT_TOKEN_RE = re.compile(r"\[\[prompt:([0-9a-fA-F-]{36})\]\]")
MAX_PROMPT_RESOLUTION_DEPTH = 20


class PromptReferenceError(ValueError):
    pass


@dataclass
class PromptBinding:
    prompt_id: str
    version: int
    surface: str | None
    name: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt_id": self.prompt_id,
            "version": int(self.version),
            "surface": self.surface,
            "name": self.name,
        }


def _normalize_surface_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            result.append(text)
    return result


class PromptReferenceResolver:
    GRAPH_FIELD_SURFACES: dict[str, dict[str, str]] = {
        "agent": {"instructions": "agent.instructions"},
        "llm": {"system_prompt": "llm.system_prompt"},
        "rag": {"query": "rag.query"},
        "vector_search": {"query": "vector_search.query"},
        "end": {"output_message": "end.output_message"},
        "user_approval": {"message": "user_approval.message"},
        "human_input": {"prompt": "human_input.prompt"},
    }

    def __init__(self, db: AsyncSession, tenant_id: UUID | None):
        self._db = db
        self._tenant_id = tenant_id

    @staticmethod
    def parse_prompt_token_ids(text: Any) -> list[UUID]:
        if not isinstance(text, str) or not text:
            return []
        result: list[UUID] = []
        for raw_id in PROMPT_TOKEN_RE.findall(text):
            try:
                result.append(UUID(str(raw_id)))
            except Exception:
                continue
        return result

    async def _get_prompt(
        self,
        prompt_id: UUID,
        *,
        cache: dict[str, PromptLibrary],
    ) -> PromptLibrary:
        cache_key = str(prompt_id)
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        stmt = select(PromptLibrary).where(PromptLibrary.id == prompt_id)
        if self._tenant_id is None:
            stmt = stmt.where(PromptLibrary.tenant_id.is_(None))
        else:
            stmt = stmt.where(or_(PromptLibrary.tenant_id == self._tenant_id, PromptLibrary.tenant_id.is_(None)))
        prompt = (await self._db.execute(stmt)).scalar_one_or_none()
        if prompt is None:
            raise PromptReferenceError(f"Referenced prompt {prompt_id} was not found in tenant/global scope")
        cache[cache_key] = prompt
        return prompt

    @staticmethod
    def _assert_prompt_allowed(prompt: PromptLibrary, *, surface: str | None) -> None:
        status = getattr(getattr(prompt, "status", None), "value", getattr(prompt, "status", None))
        if str(status or "").strip().lower() != PromptStatus.ACTIVE.value:
            raise PromptReferenceError(f"Referenced prompt {prompt.id} is archived")
        allowed_surfaces = _normalize_surface_list(getattr(prompt, "allowed_surfaces", []))
        if allowed_surfaces and surface and surface not in allowed_surfaces:
            raise PromptReferenceError(
                f"Referenced prompt {prompt.id} is not allowed on surface `{surface}`"
            )

    async def validate_text(
        self,
        text: Any,
        *,
        surface: str | None,
        current_prompt_id: UUID | None = None,
    ) -> None:
        await self.resolve_text(
            text,
            surface=surface,
            _stack=[str(current_prompt_id)] if current_prompt_id is not None else [],
            _cache={},
        )

    async def resolve_text(
        self,
        text: Any,
        *,
        surface: str | None,
        _stack: list[str] | None = None,
        _cache: dict[str, PromptLibrary] | None = None,
        _bindings: list[PromptBinding] | None = None,
        _depth: int = 0,
    ) -> tuple[str, list[dict[str, Any]]]:
        if not isinstance(text, str) or not text:
            return str(text or ""), []

        if _depth > MAX_PROMPT_RESOLUTION_DEPTH:
            raise PromptReferenceError("Prompt resolution exceeded max depth")

        stack = list(_stack or [])
        cache = _cache or {}
        bindings = _bindings or []

        async def _replace(match: re.Match[str]) -> str:
            raw_id = match.group(1)
            try:
                prompt_id = UUID(raw_id)
            except Exception as exc:
                raise PromptReferenceError(f"Invalid prompt reference token `{raw_id}`") from exc
            prompt = await self._get_prompt(prompt_id, cache=cache)
            prompt_key = str(prompt.id)
            if prompt_key in stack:
                cycle = " -> ".join([*stack, prompt_key])
                raise PromptReferenceError(f"Prompt reference cycle detected: {cycle}")
            self._assert_prompt_allowed(prompt, surface=surface)
            bindings.append(
                PromptBinding(
                    prompt_id=prompt_key,
                    version=int(prompt.version or 1),
                    surface=surface,
                    name=str(prompt.name or ""),
                )
            )
            resolved_child, _ = await self.resolve_text(
                prompt.content,
                surface=surface,
                _stack=[*stack, prompt_key],
                _cache=cache,
                _bindings=bindings,
                _depth=_depth + 1,
            )
            return resolved_child

        cursor = 0
        parts: list[str] = []
        for match in PROMPT_TOKEN_RE.finditer(text):
            parts.append(text[cursor:match.start()])
            parts.append(await _replace(match))
            cursor = match.end()
        parts.append(text[cursor:])
        return "".join(parts), [item.to_dict() for item in bindings]

    async def validate_graph_definition(self, graph_definition: dict[str, Any]) -> None:
        for _, _, surface, value in self.iter_graph_prompt_fields(graph_definition):
            await self.validate_text(value, surface=surface)

    async def resolve_graph_definition(self, graph_definition: dict[str, Any]) -> dict[str, Any]:
        resolved = deepcopy(graph_definition or {})
        nodes = resolved.get("nodes")
        if not isinstance(nodes, list):
            return resolved

        for idx, node in enumerate(nodes):
            if not isinstance(node, dict):
                continue
            config = node.get("config")
            if not isinstance(config, dict):
                continue
            node_type = str(node.get("type") or "").strip().lower()
            for field_name, surface in self.GRAPH_FIELD_SURFACES.get(node_type, {}).items():
                value = config.get(field_name)
                if isinstance(value, str) and value:
                    resolved_value, _ = await self.resolve_text(value, surface=surface)
                    nodes[idx]["config"][field_name] = resolved_value

            if node_type == "classify":
                instructions = config.get("instructions")
                if isinstance(instructions, str) and instructions:
                    resolved_value, _ = await self.resolve_text(
                        instructions,
                        surface="classify.instructions",
                    )
                    nodes[idx]["config"]["instructions"] = resolved_value
                categories = config.get("categories")
                if isinstance(categories, list):
                    for cat_idx, category in enumerate(categories):
                        if not isinstance(category, dict):
                            continue
                        description = category.get("description")
                        if isinstance(description, str) and description:
                            resolved_value, _ = await self.resolve_text(
                                description,
                                surface="classify.categories.description",
                            )
                            nodes[idx]["config"]["categories"][cat_idx]["description"] = resolved_value
        return resolved

    @classmethod
    def iter_graph_prompt_fields(
        cls,
        graph_definition: dict[str, Any],
    ) -> list[tuple[str | None, str, str, str]]:
        results: list[tuple[str | None, str, str, str]] = []
        nodes = graph_definition.get("nodes") if isinstance(graph_definition, dict) else None
        if not isinstance(nodes, list):
            return results
        for idx, node in enumerate(nodes):
            if not isinstance(node, dict):
                continue
            config = node.get("config")
            if not isinstance(config, dict):
                continue
            node_id = str(node.get("id") or "") or None
            node_type = str(node.get("type") or "").strip().lower()
            for field_name, surface in cls.GRAPH_FIELD_SURFACES.get(node_type, {}).items():
                value = config.get(field_name)
                if isinstance(value, str) and value:
                    results.append((node_id, f"/nodes/{idx}/config/{field_name}", surface, value))
            if node_type == "classify":
                instructions = config.get("instructions")
                if isinstance(instructions, str) and instructions:
                    results.append((node_id, f"/nodes/{idx}/config/instructions", "classify.instructions", instructions))
                categories = config.get("categories")
                if isinstance(categories, list):
                    for cat_idx, category in enumerate(categories):
                        if not isinstance(category, dict):
                            continue
                        description = category.get("description")
                        if isinstance(description, str) and description:
                            results.append(
                                (
                                    node_id,
                                    f"/nodes/{idx}/config/categories/{cat_idx}/description",
                                    "classify.categories.description",
                                    description,
                                )
                            )
        return results

    async def validate_schema_descriptions(self, payload: Any, *, surface: str) -> None:
        for _, value in self.iter_schema_description_fields(payload):
            await self.validate_text(value, surface=surface)

    async def resolve_schema_descriptions(self, payload: Any, *, surface: str) -> Any:
        if isinstance(payload, dict):
            resolved: dict[str, Any] = {}
            for key, value in payload.items():
                if key == "description" and isinstance(value, str):
                    resolved_value, _ = await self.resolve_text(value, surface=surface)
                    resolved[key] = resolved_value
                else:
                    resolved[key] = await self.resolve_schema_descriptions(value, surface=surface)
            return resolved
        if isinstance(payload, list):
            return [await self.resolve_schema_descriptions(item, surface=surface) for item in payload]
        return payload

    @classmethod
    def iter_schema_description_fields(
        cls,
        payload: Any,
        *,
        pointer: str = "",
    ) -> list[tuple[str, str]]:
        results: list[tuple[str, str]] = []
        if isinstance(payload, dict):
            for key, value in payload.items():
                next_pointer = f"{pointer}/{key}" if pointer else f"/{key}"
                if key == "description" and isinstance(value, str) and value:
                    results.append((next_pointer, value))
                else:
                    results.extend(cls.iter_schema_description_fields(value, pointer=next_pointer))
        elif isinstance(payload, list):
            for idx, item in enumerate(payload):
                next_pointer = f"{pointer}/{idx}" if pointer else f"/{idx}"
                results.extend(cls.iter_schema_description_fields(item, pointer=next_pointer))
        return results

    async def resolve_tool_payload(
        self,
        *,
        description: str | None,
        input_schema: dict[str, Any] | None,
        output_schema: dict[str, Any] | None,
    ) -> tuple[str | None, dict[str, Any], dict[str, Any]]:
        resolved_description = description
        if isinstance(description, str) and description:
            resolved_description, _ = await self.resolve_text(description, surface="tool.description")
        resolved_input = await self.resolve_schema_descriptions(input_schema or {}, surface="tool.schema.description")
        resolved_output = await self.resolve_schema_descriptions(output_schema or {}, surface="tool.schema.description")
        return resolved_description, resolved_input, resolved_output

    async def validate_tool_payload(
        self,
        *,
        description: str | None,
        input_schema: dict[str, Any] | None,
        output_schema: dict[str, Any] | None,
    ) -> None:
        if isinstance(description, str) and description:
            await self.validate_text(description, surface="tool.description")
        await self.validate_schema_descriptions(input_schema or {}, surface="tool.schema.description")
        await self.validate_schema_descriptions(output_schema or {}, surface="tool.schema.description")

    async def scan_usage(self, *, prompt_id: UUID) -> list[dict[str, Any]]:
        prompt_token = f"[[prompt:{prompt_id}]]"
        usages: list[dict[str, Any]] = []

        agent_stmt = select(Agent).where(or_(Agent.tenant_id == self._tenant_id, Agent.tenant_id.is_(None)))
        for agent in (await self._db.execute(agent_stmt)).scalars().all():
            graph_definition = agent.graph_definition if isinstance(agent.graph_definition, dict) else {}
            for node_id, pointer, surface, value in self.iter_graph_prompt_fields(graph_definition):
                if prompt_token in value:
                    usages.append(
                        {
                            "resource_type": "agent",
                            "resource_id": str(agent.id),
                            "resource_name": str(agent.name or ""),
                            "surface": surface,
                            "location_pointer": pointer,
                            "tenant_id": str(agent.tenant_id) if agent.tenant_id else None,
                            "node_id": node_id,
                        }
                    )

        tool_stmt = select(ToolRegistry).where(or_(ToolRegistry.tenant_id == self._tenant_id, ToolRegistry.tenant_id.is_(None)))
        for tool in (await self._db.execute(tool_stmt)).scalars().all():
            description = str(tool.description or "")
            if prompt_token in description:
                usages.append(
                    {
                        "resource_type": "tool",
                        "resource_id": str(tool.id),
                        "resource_name": str(tool.name or ""),
                        "surface": "tool.description",
                        "location_pointer": "/description",
                        "tenant_id": str(tool.tenant_id) if tool.tenant_id else None,
                        "node_id": None,
                    }
                )
            schema = tool.schema if isinstance(tool.schema, dict) else {}
            for root_key in ("input", "output"):
                schema_payload = schema.get(root_key) if isinstance(schema.get(root_key), dict) else {}
                for pointer, value in self.iter_schema_description_fields(schema_payload, pointer=f"/schema/{root_key}"):
                    if prompt_token in value:
                        usages.append(
                            {
                                "resource_type": "tool",
                                "resource_id": str(tool.id),
                                "resource_name": str(tool.name or ""),
                                "surface": "tool.schema.description",
                                "location_pointer": pointer,
                                "tenant_id": str(tool.tenant_id) if tool.tenant_id else None,
                                "node_id": None,
                            }
                        )

        draft_revision = aliased(ArtifactRevision)
        published_revision = aliased(ArtifactRevision)
        artifact_stmt = (
            select(Artifact, draft_revision, published_revision)
            .outerjoin(draft_revision, draft_revision.id == Artifact.latest_draft_revision_id)
            .outerjoin(published_revision, published_revision.id == Artifact.latest_published_revision_id)
            .where(or_(Artifact.tenant_id == self._tenant_id, Artifact.tenant_id.is_(None)))
        )
        artifact_rows = (await self._db.execute(artifact_stmt)).all()
        seen_revision_ids: set[str] = set()
        for artifact, latest_draft_revision, latest_published_revision in artifact_rows:
            for current_revision in (latest_draft_revision, latest_published_revision):
                if current_revision is None:
                    continue
                revision_key = str(current_revision.id)
                if revision_key in seen_revision_ids:
                    continue
                seen_revision_ids.add(revision_key)
                contract = current_revision.tool_contract if isinstance(current_revision.tool_contract, dict) else {}
                for contract_key in ("input_schema", "output_schema"):
                    payload = contract.get(contract_key) if isinstance(contract.get(contract_key), dict) else {}
                    for pointer, value in self.iter_schema_description_fields(
                        payload,
                        pointer=f"/tool_contract/{contract_key}",
                    ):
                        if prompt_token in value:
                            usages.append(
                                {
                                    "resource_type": "artifact",
                                    "resource_id": str(artifact.id),
                                    "resource_name": str(artifact.display_name or ""),
                                    "surface": "artifact.tool_contract.description",
                                    "location_pointer": pointer,
                                    "tenant_id": str(artifact.tenant_id) if artifact.tenant_id else None,
                                    "node_id": None,
                                }
                            )
        return usages
