from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import re
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.agents import Agent, AgentStatus
from app.db.postgres.models.artifact_runtime import Artifact, ArtifactKind, ArtifactRevision
from app.db.postgres.models.rag import ExecutablePipeline, PipelineJob, PipelineJobStatus, VisualPipeline
from app.db.postgres.models.registry import (
    ToolDefinitionScope,
    ToolImplementationType,
    ToolRegistry,
    ToolStatus,
    ToolVersion,
    set_tool_management_metadata,
)
from app.rag.pipeline.registry import ConfigFieldType, OperatorRegistry

_GENERIC_PIPELINE_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": True,
}
_GENERIC_AGENT_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": True,
}
_DEFAULT_AGENT_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "input": {
            "description": "String input or structured agent payload.",
            "anyOf": [
                {"type": "string"},
                {"type": "object", "additionalProperties": True},
            ],
        },
        "text": {"type": "string"},
        "input_text": {"type": "string"},
        "messages": {"type": "array", "items": {"type": "object"}},
        "context": {"type": "object", "additionalProperties": True},
    },
    "additionalProperties": False,
}


def _slugify(value: str, *, fallback: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return text or fallback


def _tool_semver(version_number: int | None) -> str:
    patch = max(int(version_number or 1) - 1, 0)
    return f"1.0.{patch}"


class ToolBindingService:
    def __init__(self, db: AsyncSession):
        self._db = db

    @staticmethod
    def _artifact_tool_slug(artifact: Artifact) -> str:
        display_name = str(getattr(artifact, "display_name", "") or "").strip()
        artifact_id = str(getattr(artifact, "id", "") or "").replace("-", "")
        suffix = artifact_id[:12] or "artifact"
        return _slugify(display_name, fallback=f"artifact-tool-{suffix}") + f"-{suffix}"

    async def sync_artifact_tool_binding(self, artifact: Artifact) -> ToolRegistry | None:
        if artifact.kind != ArtifactKind.TOOL_IMPL:
            await self.delete_artifact_tool_binding(artifact.id)
            return None

        revision = artifact.latest_draft_revision or artifact.latest_published_revision
        if revision is None:
            return None

        tool = await self._get_artifact_tool(artifact.id)
        slug = self._artifact_tool_slug(artifact)
        await self._ensure_slug_available(slug, exclude_tool_id=tool.id if tool else None)

        schema = self._artifact_schema_from_revision(revision)
        version = _tool_semver(revision.revision_number)
        if tool is None:
            tool = ToolRegistry(
                tenant_id=artifact.tenant_id,
                name=artifact.display_name,
                slug=slug,
                description=artifact.description,
                scope=ToolDefinitionScope.TENANT,
                schema=schema,
                config_schema=dict(revision.config_schema or {}),
                implementation_type=ToolImplementationType.ARTIFACT,
                status=ToolStatus.DRAFT,
                version=version,
                published_at=None,
                artifact_id=str(artifact.id),
                artifact_version=version,
                artifact_revision_id=None,
                is_active=True,
                is_system=False,
            )
            set_tool_management_metadata(
                tool,
                ownership="artifact_bound",
                source_object_type="artifact",
                source_object_id=artifact.id,
            )
            self._db.add(tool)
            await self._db.flush()
            return tool

        tool.name = artifact.display_name
        tool.slug = slug
        tool.description = artifact.description
        tool.schema = schema
        tool.config_schema = dict(revision.config_schema or {})
        tool.implementation_type = ToolImplementationType.ARTIFACT
        tool.artifact_id = str(artifact.id)
        tool.artifact_version = version
        tool.version = version
        tool.visual_pipeline_id = None
        tool.executable_pipeline_id = None
        if tool.status != ToolStatus.DISABLED:
            tool.status = ToolStatus.DRAFT
            tool.is_active = True
        tool.artifact_revision_id = None
        tool.published_at = None
        set_tool_management_metadata(
            tool,
            ownership="artifact_bound",
            source_object_type="artifact",
            source_object_id=artifact.id,
        )
        await self._db.flush()
        return tool

    async def publish_artifact_tool_binding(
        self,
        *,
        artifact: Artifact,
        revision: ArtifactRevision,
        created_by: UUID | None,
    ) -> ToolRegistry | None:
        tool = await self.sync_artifact_tool_binding(artifact)
        if tool is None:
            return None

        version = _tool_semver(revision.revision_number)
        tool.status = ToolStatus.PUBLISHED
        tool.is_active = True
        tool.version = version
        tool.artifact_version = version
        tool.artifact_revision_id = revision.id
        tool.published_at = datetime.utcnow()
        set_tool_management_metadata(
            tool,
            ownership="artifact_bound",
            source_object_type="artifact",
            source_object_id=artifact.id,
        )
        self._db.add(
            ToolVersion(
                tool_id=tool.id,
                version=tool.version,
                schema_snapshot=self._tool_snapshot(tool),
                created_by=created_by,
            )
        )
        await self._db.flush()
        return tool

    async def delete_artifact_tool_binding(self, artifact_id: UUID) -> None:
        tool = await self._get_artifact_tool(artifact_id)
        if tool is not None:
            await self._db.delete(tool)
            await self._db.flush()

    async def get_pipeline_tool(self, pipeline_id: UUID) -> ToolRegistry | None:
        return (
            await self._db.execute(
                select(ToolRegistry).where(ToolRegistry.visual_pipeline_id == pipeline_id)
            )
        ).scalar_one_or_none()

    async def upsert_pipeline_tool_binding(
        self,
        *,
        pipeline: VisualPipeline,
        enabled: bool,
        description: str | None = None,
        input_schema: dict[str, Any] | None = None,
    ) -> ToolRegistry | None:
        tool = await self.get_pipeline_tool(pipeline.id)
        if tool is None and not enabled:
            return None

        slug = self._pipeline_tool_slug(pipeline)
        await self._ensure_slug_available(slug, exclude_tool_id=tool.id if tool else None)

        if tool is None:
            tool = ToolRegistry(
                tenant_id=pipeline.tenant_id,
                name=pipeline.name,
                slug=slug,
                description=description if description is not None else pipeline.description,
                scope=ToolDefinitionScope.TENANT,
                schema={
                    "input": deepcopy(input_schema) if isinstance(input_schema, dict) else {"type": "object", "properties": {}, "additionalProperties": False},
                    "output": deepcopy(_GENERIC_PIPELINE_OUTPUT_SCHEMA),
                },
                config_schema={},
                implementation_type=ToolImplementationType.RAG_PIPELINE,
                status=ToolStatus.DRAFT if enabled else ToolStatus.DISABLED,
                version=_tool_semver(pipeline.version),
                published_at=None,
                visual_pipeline_id=pipeline.id,
                executable_pipeline_id=None,
                is_active=enabled,
                is_system=False,
            )
            set_tool_management_metadata(
                tool,
                ownership="pipeline_bound",
                source_object_type="pipeline",
                source_object_id=pipeline.id,
            )
            self._db.add(tool)
            await self._db.flush()
            return tool

        tool.name = pipeline.name
        tool.slug = slug
        tool.implementation_type = ToolImplementationType.RAG_PIPELINE
        tool.visual_pipeline_id = pipeline.id
        tool.artifact_id = None
        tool.artifact_version = None
        tool.artifact_revision_id = None
        tool.version = _tool_semver(pipeline.version)

        if description is not None:
            tool.description = description
        elif not str(tool.description or "").strip():
            tool.description = pipeline.description

        schema = dict(tool.schema or {})
        if isinstance(input_schema, dict):
            schema["input"] = deepcopy(input_schema)
        else:
            schema.setdefault("input", {"type": "object", "properties": {}, "additionalProperties": False})
        schema["output"] = deepcopy(_GENERIC_PIPELINE_OUTPUT_SCHEMA)
        tool.schema = schema

        if enabled:
            tool.is_active = True
            if tool.status != ToolStatus.PUBLISHED:
                tool.status = ToolStatus.DRAFT
                tool.published_at = None
        else:
            tool.is_active = False
            tool.status = ToolStatus.DISABLED
        set_tool_management_metadata(
            tool,
            ownership="pipeline_bound",
            source_object_type="pipeline",
            source_object_id=pipeline.id,
        )
        await self._db.flush()
        return tool

    async def sync_pipeline_tool_metadata(
        self,
        *,
        pipeline: VisualPipeline,
        previous_name: str | None,
        previous_description: str | None,
    ) -> ToolRegistry | None:
        tool = await self.get_pipeline_tool(pipeline.id)
        if tool is None:
            return None

        slug = self._pipeline_tool_slug(pipeline)
        await self._ensure_slug_available(slug, exclude_tool_id=tool.id)
        tool.name = pipeline.name
        tool.slug = slug
        if tool.description in {None, "", previous_description}:
            tool.description = pipeline.description
        tool.version = _tool_semver(pipeline.version)
        set_tool_management_metadata(
            tool,
            ownership="pipeline_bound",
            source_object_type="pipeline",
            source_object_id=pipeline.id,
        )
        await self._db.flush()
        return tool

    async def demote_pipeline_tool_binding(self, pipeline: VisualPipeline) -> ToolRegistry | None:
        tool = await self.get_pipeline_tool(pipeline.id)
        if tool is None:
            return None
        tool.visual_pipeline_id = pipeline.id
        tool.executable_pipeline_id = None
        tool.version = _tool_semver(pipeline.version)
        if tool.status != ToolStatus.DISABLED:
            tool.status = ToolStatus.DRAFT
            tool.is_active = True
            tool.published_at = None
        set_tool_management_metadata(
            tool,
            ownership="pipeline_bound",
            source_object_type="pipeline",
            source_object_id=pipeline.id,
        )
        await self._db.flush()
        return tool

    async def publish_pipeline_tool_binding(
        self,
        *,
        pipeline: VisualPipeline,
        executable_pipeline: ExecutablePipeline,
        created_by: UUID | None,
    ) -> ToolRegistry | None:
        tool = await self.get_pipeline_tool(pipeline.id)
        if tool is None or not tool.is_active:
            return tool

        generated_input_schema = self.build_pipeline_input_schema(executable_pipeline)
        current_input_schema = ((tool.schema or {}).get("input") if isinstance(tool.schema, dict) else None) or {}
        tool.schema = {
            "input": self.merge_generated_schema(current_input_schema, generated_input_schema),
            "output": deepcopy(_GENERIC_PIPELINE_OUTPUT_SCHEMA),
        }
        tool.name = pipeline.name
        tool.slug = self._pipeline_tool_slug(pipeline)
        tool.implementation_type = ToolImplementationType.RAG_PIPELINE
        tool.visual_pipeline_id = pipeline.id
        tool.executable_pipeline_id = executable_pipeline.id
        tool.status = ToolStatus.PUBLISHED
        tool.is_active = True
        tool.version = _tool_semver(executable_pipeline.version)
        tool.published_at = datetime.utcnow()
        set_tool_management_metadata(
            tool,
            ownership="pipeline_bound",
            source_object_type="pipeline",
            source_object_id=pipeline.id,
        )
        self._db.add(
            ToolVersion(
                tool_id=tool.id,
                version=tool.version,
                schema_snapshot=self._tool_snapshot(tool),
                created_by=created_by,
            )
        )
        await self._db.flush()
        return tool

    async def delete_pipeline_tool_binding(self, pipeline_id: UUID) -> None:
        tool = await self.get_pipeline_tool(pipeline_id)
        if tool is not None:
            await self._db.delete(tool)
            await self._db.flush()

    async def get_agent_tool(self, agent_id: UUID) -> ToolRegistry | None:
        return (
            await self._db.execute(
                select(ToolRegistry).where(ToolRegistry.slug == self._agent_tool_slug(agent_id))
            )
        ).scalar_one_or_none()

    async def export_agent_tool_binding(
        self,
        *,
        agent: Agent,
        name: str | None = None,
        description: str | None = None,
        input_schema: dict[str, Any] | None = None,
        created_by: UUID | None = None,
    ) -> ToolRegistry:
        tool = await self.get_agent_tool(agent.id)
        config_schema = self._agent_tool_config_schema(agent=agent, existing_tool=tool)
        desired_status = self._agent_tool_status(agent)
        desired_version = _tool_semver(agent.version)
        schema = dict(tool.schema or {}) if tool is not None and isinstance(tool.schema, dict) else {}
        if input_schema is not None:
            schema["input"] = deepcopy(input_schema)
        else:
            schema.setdefault("input", deepcopy(_DEFAULT_AGENT_INPUT_SCHEMA))
        schema["output"] = deepcopy(_GENERIC_AGENT_OUTPUT_SCHEMA)

        if tool is None:
            tool = ToolRegistry(
                tenant_id=agent.tenant_id,
                name=str(name or agent.name).strip() or agent.name,
                slug=self._agent_tool_slug(agent.id),
                description=description if description is not None else agent.description,
                scope=ToolDefinitionScope.TENANT,
                schema=schema,
                config_schema=config_schema,
                implementation_type=ToolImplementationType.AGENT_CALL,
                status=desired_status,
                version=desired_version,
                published_at=datetime.utcnow() if desired_status == ToolStatus.PUBLISHED else None,
                is_active=True,
                is_system=False,
            )
            set_tool_management_metadata(
                tool,
                ownership="agent_bound",
                source_object_type="agent",
                source_object_id=agent.id,
            )
            self._db.add(tool)
            await self._db.flush()
        else:
            if name is not None:
                tool.name = str(name).strip() or agent.name
            elif not str(tool.name or "").strip():
                tool.name = agent.name
            if description is not None:
                tool.description = description
            elif tool.description is None:
                tool.description = agent.description
            tool.schema = schema
            tool.config_schema = config_schema
            tool.implementation_type = ToolImplementationType.AGENT_CALL
            tool.status = desired_status
            tool.version = desired_version
            tool.is_active = True
            tool.is_system = False
            tool.published_at = datetime.utcnow() if desired_status == ToolStatus.PUBLISHED else None
            set_tool_management_metadata(
                tool,
                ownership="agent_bound",
                source_object_type="agent",
                source_object_id=agent.id,
            )

        await self._maybe_snapshot_published_tool(tool=tool, created_by=created_by)
        await self._db.flush()
        return tool

    async def sync_exported_agent_tool_binding(
        self,
        *,
        agent: Agent,
        created_by: UUID | None = None,
    ) -> ToolRegistry | None:
        existing = await self.get_agent_tool(agent.id)
        if existing is None:
            return None
        return await self.export_agent_tool_binding(agent=agent, created_by=created_by)

    async def delete_agent_tool_binding(self, agent_id: UUID) -> None:
        tool = await self.get_agent_tool(agent_id)
        if tool is not None:
            await self._db.delete(tool)
            await self._db.flush()

    def build_pipeline_input_schema(self, executable_pipeline: ExecutablePipeline) -> dict[str, Any]:
        dag = ((executable_pipeline.compiled_graph or {}).get("dag") or [])
        registry = OperatorRegistry.get_instance()
        tenant_id = str(executable_pipeline.tenant_id) if executable_pipeline.tenant_id else None
        root_steps = [step for step in dag if not (step.get("depends_on") or [])]

        if len(root_steps) == 1:
            return self._step_input_object(root_steps[0], registry=registry, tenant_id=tenant_id)

        properties: dict[str, Any] = {}
        required: list[str] = []
        for step in root_steps:
            step_id = str(step.get("step_id") or step.get("operator") or "step")
            properties[step_id] = self._step_input_object(step, registry=registry, tenant_id=tenant_id)
            required.append(step_id)
        return {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }

    def merge_generated_schema(self, existing: dict[str, Any] | None, generated: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(existing, dict):
            return deepcopy(generated)
        merged = deepcopy(generated)
        for key in ("description", "examples", "default", "title"):
            if key in existing:
                merged[key] = deepcopy(existing[key])

        generated_props = generated.get("properties")
        existing_props = existing.get("properties")
        if isinstance(generated_props, dict) and isinstance(existing_props, dict):
            merged_props: dict[str, Any] = {}
            for prop_name, generated_prop in generated_props.items():
                merged_props[prop_name] = self.merge_generated_schema(
                    existing_props.get(prop_name) if isinstance(existing_props, dict) else None,
                    generated_prop,
                )
            merged["properties"] = merged_props
        return merged

    async def run_pipeline_tool(
        self,
        *,
        tenant_id: UUID,
        executable_pipeline_id: UUID,
        input_payload: dict[str, Any],
    ) -> tuple[dict[str, Any], PipelineJob]:
        from app.rag.pipeline.executor import PipelineExecutor

        job = PipelineJob(
            tenant_id=tenant_id,
            executable_pipeline_id=executable_pipeline_id,
            status=PipelineJobStatus.QUEUED,
            input_params=input_payload,
            triggered_by=None,
        )
        self._db.add(job)
        await self._db.commit()
        await PipelineExecutor(self._db).execute_job(job.id, artifact_queue_class="artifact_prod_interactive")
        await self._db.refresh(job)
        if job.status == PipelineJobStatus.FAILED:
            raise RuntimeError(job.error_message or "Pipeline execution failed")
        output = job.output
        if isinstance(output, dict):
            return output, job
        return {"result": output}, job

    async def _get_artifact_tool(self, artifact_id: UUID) -> ToolRegistry | None:
        return (
            await self._db.execute(
                select(ToolRegistry).where(ToolRegistry.artifact_id == str(artifact_id))
            )
        ).scalar_one_or_none()

    async def _ensure_slug_available(self, slug: str, *, exclude_tool_id: UUID | None) -> None:
        existing = (
            await self._db.execute(select(ToolRegistry).where(ToolRegistry.slug == slug))
        ).scalar_one_or_none()
        if existing is not None and existing.id != exclude_tool_id:
            raise ValueError(f"Tool slug '{slug}' is already in use")

    def _artifact_schema_from_revision(self, revision: ArtifactRevision) -> dict[str, Any]:
        contract = dict(revision.tool_contract or {})
        return {
            "input": dict(contract.get("input_schema") or {}),
            "output": dict(contract.get("output_schema") or {}),
        }

    def _pipeline_tool_slug(self, pipeline: VisualPipeline) -> str:
        base = _slugify(pipeline.name, fallback="pipeline-tool")
        return f"{base}-pipeline-{str(pipeline.id).replace('-', '')[:8]}"

    def _agent_tool_slug(self, agent_id: UUID) -> str:
        return f"agent-tool-{str(agent_id).replace('-', '')[:12]}"

    def _agent_tool_status(self, agent: Agent) -> ToolStatus:
        status_text = str(getattr(getattr(agent, "status", None), "value", getattr(agent, "status", ""))).lower()
        if status_text == AgentStatus.published.value:
            return ToolStatus.PUBLISHED
        return ToolStatus.DRAFT

    def _agent_tool_config_schema(self, *, agent: Agent, existing_tool: ToolRegistry | None) -> dict[str, Any]:
        existing_config = dict(existing_tool.config_schema or {}) if existing_tool and isinstance(existing_tool.config_schema, dict) else {}
        existing_execution = existing_config.get("execution") if isinstance(existing_config.get("execution"), dict) else {}
        timeout_s = existing_execution.get("timeout_s")
        if timeout_s is None:
            constraints = agent.execution_constraints if isinstance(agent.execution_constraints, dict) else {}
            timeout_s = int(constraints.get("timeout_seconds") or 60)
        return {
            "implementation": {
                "type": "agent_call",
                "target_agent_id": str(agent.id),
                "target_agent_slug": agent.slug,
                "mode": "sync",
            },
            "execution": {
                "timeout_s": int(timeout_s or 60),
                "is_pure": False,
            },
            "agent_binding": {
                "agent_id": str(agent.id),
                "owned_by_source": True,
            },
        }

    def _tool_snapshot(self, tool: ToolRegistry) -> dict[str, Any]:
        return {
            "schema": deepcopy(tool.schema or {}),
            "config_schema": deepcopy(tool.config_schema or {}),
            "implementation_type": getattr(tool.implementation_type, "value", tool.implementation_type),
            "version": tool.version,
            "artifact_id": tool.artifact_id,
            "artifact_version": tool.artifact_version,
            "artifact_revision_id": str(tool.artifact_revision_id) if tool.artifact_revision_id else None,
            "visual_pipeline_id": str(tool.visual_pipeline_id) if tool.visual_pipeline_id else None,
            "executable_pipeline_id": str(tool.executable_pipeline_id) if tool.executable_pipeline_id else None,
        }

    async def _maybe_snapshot_published_tool(self, *, tool: ToolRegistry, created_by: UUID | None) -> None:
        if tool.status != ToolStatus.PUBLISHED:
            return
        existing = (
            await self._db.execute(
                select(ToolVersion).where(ToolVersion.tool_id == tool.id, ToolVersion.version == tool.version).limit(1)
            )
        ).scalar_one_or_none()
        if existing is not None:
            return
        self._db.add(
            ToolVersion(
                tool_id=tool.id,
                version=tool.version,
                schema_snapshot=self._tool_snapshot(tool),
                created_by=created_by,
            )
        )

    def _step_input_object(
        self,
        step: dict[str, Any],
        *,
        registry: OperatorRegistry,
        tenant_id: str | None,
    ) -> dict[str, Any]:
        operator_id = step.get("operator")
        if not operator_id:
            return {"type": "object", "properties": {}, "additionalProperties": False}
        spec = registry.get(operator_id, tenant_id)
        if spec is None:
            return {"type": "object", "properties": {}, "additionalProperties": False}

        properties: dict[str, Any] = {}
        required: list[str] = []
        for field in list(spec.required_config or []) + list(spec.optional_config or []):
            if not field.runtime:
                continue
            properties[field.name] = self._json_schema_for_field(field)
            if field.required:
                required.append(field.name)

        payload = {
            "type": "object",
            "properties": properties,
            "additionalProperties": False,
        }
        if required:
            payload["required"] = required
        return payload

    def _json_schema_for_field(self, field: Any) -> dict[str, Any]:
        if getattr(field, "field_type", None) == ConfigFieldType.JSON and isinstance(field.json_schema, dict):
            schema = deepcopy(field.json_schema)
        else:
            schema = {}
            field_type = getattr(field.field_type, "value", field.field_type)
            if field_type == ConfigFieldType.INTEGER.value:
                schema["type"] = "integer"
            elif field_type == ConfigFieldType.FLOAT.value:
                schema["type"] = "number"
            elif field_type == ConfigFieldType.BOOLEAN.value:
                schema["type"] = "boolean"
            elif field_type == ConfigFieldType.JSON.value:
                schema.update({"type": "object", "additionalProperties": True})
            else:
                schema["type"] = "string"

        if field.description:
            schema["description"] = field.description
        if getattr(field, "default", None) is not None:
            schema["default"] = deepcopy(field.default)
        if getattr(field, "options", None):
            schema["enum"] = list(field.options)
        if getattr(field, "min_value", None) is not None:
            schema["minimum"] = field.min_value
        if getattr(field, "max_value", None) is not None:
            schema["maximum"] = field.max_value
        return schema
