from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.engine import sessionmaker
from app.db.postgres.models.rag import ExecutablePipeline, PipelineJob, PipelineJobStatus, PipelineType, VisualPipeline
from app.graph_authoring import (
    collect_rag_authoring_issues,
    critical_rag_write_issues,
    dedupe_issues,
    normalize_rag_graph_definition,
    rag_catalog_item,
    rag_instance_contract,
    rag_node_spec,
)
from app.rag.pipeline.compiler import PipelineCompiler, VisualPipeline as CompilerVisualPipeline
from app.rag.pipeline.custom_operator_sync import sync_custom_operators
from app.rag.pipeline.executor import PipelineExecutor
from app.rag.pipeline.input_storage import PipelineInputStorage
from app.rag.pipeline.registry import ConfigFieldType, OperatorRegistry
from app.services.control_plane.context import ControlPlaneContext
from app.services.control_plane.contracts import ListPage, ListQuery, OperationResult
from app.services.control_plane.errors import conflict, not_found, validation
from app.services.rag_executable_state import StaleExecutablePipelineError, ensure_executable_pipeline_is_current
from app.services.tool_binding_service import ToolBindingService


async def dispatch_pipeline_job_background(
    job_id: UUID,
    *,
    artifact_queue_class: str = "artifact_prod_background",
) -> None:
    """Execute a pipeline job in its own session so async callers can fire-and-forget."""
    async with sessionmaker() as session:
        executor = PipelineExecutor(session)
        await executor.execute_job(job_id, artifact_queue_class=artifact_queue_class)


@dataclass(frozen=True)
class CreatePipelineInput:
    name: str
    pipeline_type: str
    description: str | None = None
    nodes: list[dict[str, Any]] | None = None
    edges: list[dict[str, Any]] | None = None
    org_unit_id: UUID | None = None


@dataclass(frozen=True)
class UpdatePipelineInput:
    name: str | None = None
    description: str | None = None
    nodes: list[dict[str, Any]] | None = None
    edges: list[dict[str, Any]] | None = None


class RagAdminService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.registry = OperatorRegistry.get_instance()

    @staticmethod
    def _require_project_id(ctx: ControlPlaneContext) -> UUID:
        if ctx.project_id is None:
            raise validation("Active project context is required")
        return ctx.project_id

    async def list_visual_pipelines(self, *, ctx: ControlPlaneContext, query: ListQuery) -> ListPage:
        project_id = self._require_project_id(ctx)
        stmt = (
            select(VisualPipeline)
            .where(VisualPipeline.organization_id == ctx.organization_id)
            .where(VisualPipeline.project_id == project_id)
            .order_by(VisualPipeline.updated_at.desc())
            .offset(query.skip)
            .limit(query.limit)
        )
        total_stmt = (
            select(func.count())
            .select_from(VisualPipeline)
            .where(VisualPipeline.organization_id == ctx.organization_id, VisualPipeline.project_id == project_id)
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        total = int(await self.db.scalar(total_stmt) or 0)
        return ListPage(items=[self.serialize_pipeline(row, view=query.view) for row in rows], total=total, query=query)

    async def operators_catalog(self, *, ctx: ControlPlaneContext, pipeline_type: str) -> dict[str, Any]:
        await sync_custom_operators(self.db, ctx.organization_id)
        if not str(pipeline_type or "").strip():
            raise validation("pipeline_type is required", field="pipeline_type")
        normalized_pipeline_type = self._normalize_pipeline_type(pipeline_type)
        items = [
            rag_catalog_item(spec).model_dump(mode="json")
            for spec in self._operators_for_pipeline_type(
                normalized_pipeline_type,
                organization_id=str(ctx.organization_id),
            )
        ]
        return {"operators": items}

    async def operators_schema(self, *, ctx: ControlPlaneContext, pipeline_type: str, operator_ids: list[str]) -> dict[str, Any]:
        await sync_custom_operators(self.db, ctx.organization_id)
        if not str(pipeline_type or "").strip():
            raise validation("pipeline_type is required", field="pipeline_type")
        normalized_pipeline_type = self._normalize_pipeline_type(pipeline_type)
        normalized = [str(item).strip() for item in operator_ids if str(item).strip()]
        if not normalized:
            raise validation("operator_ids must be a non-empty array", field="operator_ids")
        schemas: dict[str, Any] = {}
        unknown: list[str] = []
        disallowed: list[str] = []
        for operator_id in normalized:
            spec = self.registry.get(operator_id, organization_id=str(ctx.organization_id))
            if spec is None:
                unknown.append(operator_id)
                continue
            if not self._operator_allowed_for_pipeline_type(spec, normalized_pipeline_type):
                disallowed.append(operator_id)
                continue
            schemas[operator_id] = rag_node_spec(spec).model_dump(mode="json", exclude_none=True)
        if unknown:
            raise validation("Unknown operator ids", field="operator_ids", unknown=unknown)
        if disallowed:
            raise validation(
                "Operators are not available for the requested pipeline_type",
                field="operator_ids",
                pipeline_type=normalized_pipeline_type.value,
                disallowed=disallowed,
            )
        return {"specs": schemas, "instance_contract": rag_instance_contract()}

    async def create_pipeline(self, *, ctx: ControlPlaneContext, params: CreatePipelineInput) -> dict[str, Any]:
        name = str(params.name or "").strip()
        if not name:
            raise validation("name is required", field="name")
        if not str(params.pipeline_type or "").strip():
            raise validation("pipeline_type is required", field="pipeline_type")
        project_id = self._require_project_id(ctx)
        await sync_custom_operators(self.db, ctx.organization_id)
        normalized_graph = self._normalize_graph_for_write(
            nodes=params.nodes,
            edges=params.edges,
            organization_id=str(ctx.organization_id),
        )
        pipeline = VisualPipeline(
            organization_id=ctx.organization_id,
            project_id=project_id,
            org_unit_id=params.org_unit_id,
            name=name,
            description=params.description,
            nodes=list(normalized_graph["nodes"]),
            edges=list(normalized_graph["edges"]),
            version=1,
            is_published=False,
            pipeline_type=self._normalize_pipeline_type(params.pipeline_type),
            created_by=ctx.user_id,
        )
        self.db.add(pipeline)
        await self.db.commit()
        await self.db.refresh(pipeline)
        return {"id": str(pipeline.id), "status": "created", "pipeline": self.serialize_pipeline(pipeline)}

    async def update_pipeline(self, *, ctx: ControlPlaneContext, pipeline_id: UUID, params: UpdatePipelineInput) -> dict[str, Any]:
        pipeline = await self._get_pipeline(ctx, pipeline_id)
        previous_name = pipeline.name
        previous_description = pipeline.description
        was_published = bool(pipeline.is_published)
        await sync_custom_operators(self.db, ctx.organization_id)
        if was_published:
            pipeline.version = int(pipeline.version or 0) + 1
            pipeline.is_published = False
        if params.name is not None:
            name = str(params.name).strip()
            if not name:
                raise validation("name cannot be blank", field="name")
            pipeline.name = name
        if params.description is not None:
            pipeline.description = params.description
        if params.nodes is not None:
            normalized_graph = self._normalize_graph_for_write(
                nodes=params.nodes,
                edges=params.edges if params.edges is not None else pipeline.edges,
                organization_id=str(ctx.organization_id),
            )
            pipeline.nodes = list(normalized_graph["nodes"])
            pipeline.edges = list(normalized_graph["edges"])
        elif params.edges is not None:
            normalized_graph = self._normalize_graph_for_write(
                nodes=pipeline.nodes,
                edges=params.edges,
                organization_id=str(ctx.organization_id),
            )
            pipeline.nodes = list(normalized_graph["nodes"])
            pipeline.edges = list(normalized_graph["edges"])
        pipeline.updated_at = datetime.utcnow()
        binding_service = ToolBindingService(self.db)
        await binding_service.sync_pipeline_tool_metadata(
            pipeline=pipeline,
            previous_name=previous_name,
            previous_description=previous_description,
        )
        if was_published:
            await binding_service.demote_pipeline_tool_binding(pipeline)
        await self.db.commit()
        await self.db.refresh(pipeline)
        return {"status": "updated", "version": pipeline.version, "pipeline": self.serialize_pipeline(pipeline)}

    async def get_executable_pipeline(self, *, ctx: ControlPlaneContext, executable_pipeline_id: UUID) -> dict[str, Any]:
        executable = await self._get_executable_pipeline(ctx, executable_pipeline_id)
        return self.serialize_executable_pipeline(executable)

    async def compile_pipeline(self, *, ctx: ControlPlaneContext, pipeline_id: UUID) -> dict[str, Any]:
        pipeline = await self._get_pipeline(ctx, pipeline_id)
        await sync_custom_operators(self.db, ctx.organization_id)
        normalized_graph = normalize_rag_graph_definition(
            {"nodes": list(pipeline.nodes or []), "edges": list(pipeline.edges or [])},
            organization_id=str(ctx.organization_id),
            registry=self.registry,
        )
        compile_result = PipelineCompiler().compile(
            CompilerVisualPipeline(
                id=pipeline.id,
                organization_id=pipeline.organization_id,
                org_unit_id=pipeline.org_unit_id,
                name=pipeline.name,
                description=pipeline.description,
                nodes=list(normalized_graph["nodes"]),
                edges=list(normalized_graph["edges"]),
                version=pipeline.version,
                pipeline_type=pipeline.pipeline_type,
                is_published=pipeline.is_published,
            ),
            compiled_by=str(ctx.user_id) if ctx.user_id else "",
            organization_id=str(ctx.organization_id),
            require_published_artifacts=True,
        )
        if not getattr(compile_result, "success", False):
            authoring_issues = collect_rag_authoring_issues(
                normalized_graph,
                organization_id=str(ctx.organization_id),
                registry=self.registry,
            )
            return {
                "success": False,
                "errors": dedupe_issues(
                    authoring_issues
                    + [self._dump(item) for item in list(getattr(compile_result, "errors", []) or [])]
                ),
                "warnings": [self._dump(item) for item in list(getattr(compile_result, "warnings", []) or [])],
            }
        executable = ExecutablePipeline(
            visual_pipeline_id=pipeline.id,
            organization_id=pipeline.organization_id,
            project_id=pipeline.project_id,
            version=pipeline.version,
            compiled_graph=compile_result.executable_pipeline.model_dump(mode="json") if hasattr(compile_result.executable_pipeline, "model_dump") else {},
            is_valid=True,
            pipeline_type=pipeline.pipeline_type,
            compiled_by=ctx.user_id,
        )
        self.db.add(executable)
        pipeline.is_published = True
        pipeline.updated_at = datetime.utcnow()
        await ToolBindingService(self.db).publish_pipeline_tool_binding(
            pipeline=pipeline,
            executable_pipeline=executable,
            created_by=ctx.user_id,
        )
        await self.db.commit()
        await self.db.refresh(executable)
        return {
            "success": True,
            "executable_pipeline_id": str(executable.id),
            "version": pipeline.version,
            "warnings": [self._dump(item) for item in list(getattr(compile_result, "warnings", []) or [])],
        }

    def _normalize_graph_for_write(
        self,
        *,
        nodes: list[dict[str, Any]] | None,
        edges: list[dict[str, Any]] | None,
        organization_id: str,
    ) -> dict[str, Any]:
        normalized_graph = normalize_rag_graph_definition(
            {"nodes": list(nodes or []), "edges": list(edges or [])},
            organization_id=organization_id,
            registry=self.registry,
        )
        issues = critical_rag_write_issues(
            collect_rag_authoring_issues(
                normalized_graph,
                organization_id=organization_id,
                registry=self.registry,
            )
        )
        if issues:
            raise validation("Pipeline write rejected", errors=issues)
        return normalized_graph

    async def get_executable_input_schema(self, *, ctx: ControlPlaneContext, executable_pipeline_id: UUID) -> dict[str, Any]:
        executable = await self._get_executable_pipeline(ctx, executable_pipeline_id)
        dag = (executable.compiled_graph or {}).get("dag") or []
        await sync_custom_operators(self.db, ctx.organization_id)
        return {"steps": self._build_input_schema_steps(dag=dag, organization_id=str(ctx.organization_id))}

    async def create_job(
        self,
        *,
        ctx: ControlPlaneContext,
        executable_pipeline_id: UUID,
        input_params: dict[str, Any],
    ) -> dict[str, Any]:
        executable = await self._get_executable_pipeline(ctx, executable_pipeline_id)
        pipeline = await self._get_pipeline(ctx, executable.visual_pipeline_id)
        try:
            ensure_executable_pipeline_is_current(pipeline, executable)
        except StaleExecutablePipelineError as exc:
            raise conflict(str(exc), **exc.to_detail()) from exc
        await sync_custom_operators(self.db, ctx.organization_id)
        normalized, errors = self._validate_input_params(
            dag=(executable.compiled_graph or {}).get("dag") or [],
            organization_id=str(ctx.organization_id),
            input_params=input_params if isinstance(input_params, dict) else {},
        )
        if errors:
            raise validation("Invalid pipeline input", errors=errors)
        job = PipelineJob(
            organization_id=ctx.organization_id,
            project_id=executable.project_id,
            executable_pipeline_id=executable_pipeline_id,
            status=PipelineJobStatus.QUEUED,
            input_params=normalized,
            triggered_by=ctx.user_id,
        )
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)
        return OperationResult(
            operation_id=str(job.id),
            kind="pipeline_job",
            status=str(getattr(job.status, "value", job.status)).lower(),
            metadata={"executable_pipeline_id": str(executable_pipeline_id)},
        ).to_dict()

    async def get_job(self, *, ctx: ControlPlaneContext, job_id: UUID) -> dict[str, Any]:
        project_id = self._require_project_id(ctx)
        job = await self.db.scalar(
            select(PipelineJob).where(
                PipelineJob.id == job_id,
                PipelineJob.organization_id == ctx.organization_id,
                PipelineJob.project_id == project_id,
            )
        )
        if job is None:
            raise not_found("Job not found", job_id=str(job_id))
        return OperationResult(
            operation_id=str(job.id),
            kind="pipeline_job",
            status=str(getattr(job.status, "value", job.status)).lower(),
            result=self.serialize_job(job),
        ).to_dict()

    async def _get_pipeline(self, ctx: ControlPlaneContext, pipeline_id: UUID) -> VisualPipeline:
        project_id = self._require_project_id(ctx)
        pipeline = await self.db.scalar(
            select(VisualPipeline).where(
                VisualPipeline.id == pipeline_id,
                VisualPipeline.organization_id == ctx.organization_id,
                VisualPipeline.project_id == project_id,
            )
        )
        if pipeline is None:
            raise not_found("Pipeline not found", pipeline_id=str(pipeline_id))
        return pipeline

    async def _get_executable_pipeline(self, ctx: ControlPlaneContext, executable_pipeline_id: UUID) -> ExecutablePipeline:
        project_id = self._require_project_id(ctx)
        executable = await self.db.scalar(
            select(ExecutablePipeline).where(
                ExecutablePipeline.id == executable_pipeline_id,
                ExecutablePipeline.organization_id == ctx.organization_id,
                ExecutablePipeline.project_id == project_id,
            )
        )
        if executable is None:
            raise not_found("Executable pipeline not found", executable_pipeline_id=str(executable_pipeline_id))
        return executable

    @staticmethod
    def serialize_pipeline(pipeline: VisualPipeline, *, view: str = "full") -> dict[str, Any]:
        payload = {
            "id": str(pipeline.id),
            "organization_id": str(pipeline.organization_id),
            "org_unit_id": str(pipeline.org_unit_id) if pipeline.org_unit_id else None,
            "name": pipeline.name,
            "description": pipeline.description,
            "version": int(pipeline.version or 0),
            "is_published": bool(pipeline.is_published),
            "pipeline_type": getattr(pipeline.pipeline_type, "value", pipeline.pipeline_type),
            "created_at": pipeline.created_at.isoformat() if pipeline.created_at else None,
            "updated_at": pipeline.updated_at.isoformat() if pipeline.updated_at else None,
        }
        if view == "summary":
            return payload
        payload.update(
            {
                "nodes": list(pipeline.nodes or []),
                "edges": list(pipeline.edges or []),
            }
        )
        return payload

    @staticmethod
    def serialize_executable_pipeline(executable: ExecutablePipeline) -> dict[str, Any]:
        return {
            "id": str(executable.id),
            "visual_pipeline_id": str(executable.visual_pipeline_id),
            "organization_id": str(executable.organization_id),
            "project_id": str(executable.project_id) if executable.project_id else None,
            "version": int(executable.version or 0),
            "pipeline_type": getattr(executable.pipeline_type, "value", executable.pipeline_type),
            "compiled_graph": dict(executable.compiled_graph or {}),
            "is_valid": bool(executable.is_valid),
            "compiled_by": str(executable.compiled_by) if executable.compiled_by else None,
            "created_at": executable.created_at.isoformat() if executable.created_at else None,
        }

    @staticmethod
    def serialize_job(job: PipelineJob) -> dict[str, Any]:
        return {
            "id": str(job.id),
            "executable_pipeline_id": str(job.executable_pipeline_id),
            "project_id": str(job.project_id) if job.project_id else None,
            "status": str(getattr(job.status, "value", job.status)).lower(),
            "input_params": dict(job.input_params or {}),
            "output": job.output,
            "error_message": job.error_message,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "updated_at": job.updated_at.isoformat() if job.updated_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        }

    def _build_input_schema_steps(self, *, dag: list[dict[str, Any]], organization_id: str) -> list[dict[str, Any]]:
        steps: list[dict[str, Any]] = []
        for step in dag:
            if step.get("depends_on"):
                continue
            operator_id = step.get("operator")
            if not operator_id:
                continue
            spec = self.registry.get(operator_id, organization_id)
            if spec is None:
                continue
            config = step.get("config") if isinstance(step.get("config"), dict) else {}
            fields: list[dict[str, Any]] = []
            required_names = set(spec.get_required_field_names())
            for field in list(spec.required_config or []) + list(spec.optional_config or []):
                if not getattr(field, "runtime", False):
                    continue
                fields.append(
                    {
                        "name": field.name,
                        "field_type": field.field_type.value,
                        "required": bool(field.required or field.name in required_names),
                        "runtime": bool(field.runtime),
                        "default": field.default,
                        "description": field.description,
                        "options": field.options,
                        "placeholder": field.placeholder,
                        "required_capability": field.required_capability,
                        "operator_id": spec.operator_id,
                        "operator_display_name": spec.display_name,
                        "step_id": step.get("step_id") or operator_id,
                        "json_schema": field.json_schema,
                        "min_value": field.min_value,
                        "max_value": field.max_value,
                    }
                )
            steps.append(
                {
                    "step_id": step.get("step_id") or operator_id,
                    "operator_id": operator_id,
                    "operator_display_name": spec.display_name,
                    "category": getattr(getattr(spec, "category", None), "value", getattr(spec, "category", None)),
                    "config": config,
                    "fields": fields,
                }
            )
        return steps

    def _validate_input_params(
        self,
        *,
        dag: list[dict[str, Any]],
        organization_id: str,
        input_params: dict[str, Any],
    ) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]]]:
        steps = self._build_input_schema_steps(dag=dag, organization_id=organization_id)
        step_ids = [step["step_id"] for step in steps]
        if len(step_ids) == 1 and step_ids[0] not in input_params:
            normalized = {step_ids[0]: dict(input_params)}
        else:
            normalized = {}
            for step_id in step_ids:
                value = input_params.get(step_id, {})
                if value is None:
                    value = {}
                if not isinstance(value, dict):
                    return {}, [{"step_id": step_id, "field": "__root__", "message": "Step input must be an object"}]
                normalized[step_id] = value
        errors: list[dict[str, str]] = []
        storage = PipelineInputStorage()
        for step in steps:
            step_params = normalized.get(step["step_id"], {})
            allowed = {field["name"]: field for field in step["fields"]}
            config = step["config"] if isinstance(step["config"], dict) else {}
            for key in step_params:
                if key not in allowed:
                    errors.append({"step_id": step["step_id"], "field": key, "message": "Unexpected runtime field"})
            for field in step["fields"]:
                provided = field["name"] in step_params
                has_config = field["name"] in config and config.get(field["name"]) is not None
                if field["required"] and not provided and not has_config and field.get("default") is None:
                    errors.append({"step_id": step["step_id"], "field": field["name"], "message": "Missing required field"})
                    continue
                if not provided:
                    continue
                errors.extend(self._validate_field_value(step["step_id"], field, step_params[field["name"]], storage))
        return normalized, errors

    @staticmethod
    def _validate_field_value(step_id: str, field: dict[str, Any], value: Any, storage: PipelineInputStorage) -> list[dict[str, str]]:
        errors: list[dict[str, str]] = []
        field_type = field.get("field_type")
        name = str(field.get("name"))
        if field_type == ConfigFieldType.STRING.value and not isinstance(value, str):
            errors.append({"step_id": step_id, "field": name, "message": "Must be a string"})
        elif field_type == ConfigFieldType.SECRET.value and (not isinstance(value, str) or not value.startswith("$secret:")):
            errors.append({"step_id": step_id, "field": name, "message": "Must be a secret reference"})
        elif field_type == ConfigFieldType.SELECT.value:
            if not isinstance(value, str):
                errors.append({"step_id": step_id, "field": name, "message": "Must be a string"})
            elif field.get("options") and value not in list(field["options"] or []):
                errors.append({"step_id": step_id, "field": name, "message": f"Must be one of: {field['options']}"})
        elif field_type == ConfigFieldType.INTEGER.value and (not isinstance(value, int) or isinstance(value, bool)):
            errors.append({"step_id": step_id, "field": name, "message": "Must be an integer"})
        elif field_type == ConfigFieldType.FLOAT.value and (not isinstance(value, (int, float)) or isinstance(value, bool)):
            errors.append({"step_id": step_id, "field": name, "message": "Must be a number"})
        elif field_type == ConfigFieldType.BOOLEAN.value and not isinstance(value, bool):
            errors.append({"step_id": step_id, "field": name, "message": "Must be a boolean"})
        elif field_type == ConfigFieldType.JSON.value and not isinstance(value, (dict, list, str)):
            errors.append({"step_id": step_id, "field": name, "message": "Must be an object, list, or JSON string"})
        elif field_type == ConfigFieldType.FILE_PATH.value and isinstance(value, str):
            if storage.is_managed_path(value) and not storage.path_exists(value):
                errors.append({"step_id": step_id, "field": name, "message": "Uploaded file not found"})
        return errors

    @staticmethod
    def _normalize_pipeline_type(value: str | None) -> PipelineType:
        raw = str(value or PipelineType.RETRIEVAL.value).strip().lower()
        try:
            return PipelineType(raw)
        except ValueError as exc:
            raise validation("Unsupported pipeline_type", field="pipeline_type", value=value) from exc

    def _operators_for_pipeline_type(
        self,
        pipeline_type: PipelineType,
        *,
        organization_id: str,
    ) -> list:
        return [
            spec
            for spec in self.registry.list_all(organization_id)
            if self._operator_allowed_for_pipeline_type(spec, pipeline_type)
        ]

    @staticmethod
    def _operator_allowed_for_pipeline_type(spec, pipeline_type: PipelineType) -> bool:
        category = str(getattr(getattr(spec, "category", None), "value", getattr(spec, "category", "")) or "").strip().lower()
        if category == "custom":
            return True
        if pipeline_type == PipelineType.INGESTION:
            return category in {"source", "normalization", "enrichment", "chunking", "utility", "embedding", "storage"}
        return category in {"input", "utility", "embedding", "retrieval", "reranking", "output"}

    @staticmethod
    def _dump(value: Any) -> Any:
        if hasattr(value, "model_dump"):
            return value.model_dump()
        if isinstance(value, dict):
            return dict(value)
        return value
