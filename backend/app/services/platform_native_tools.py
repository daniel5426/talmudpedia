from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any, Awaitable, Callable
from uuid import UUID

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.api.dependencies import get_current_principal
from app.api.routers import agent_graph_mutations, agents, artifacts, knowledge_stores, models, orchestration_internal, rag_graph_mutations, rag_operator_contracts, rag_pipelines, settings, tools
from app.api.schemas.artifacts import ArtifactConvertKindRequest, ArtifactCreate, ArtifactTestRequest, ArtifactUpdate
from app.api.routers.agents import CreateAgentRequest, ExecuteAgentRequest, NodeSchemaRequest, UpdateAgentRequest, get_node_schemas, list_node_catalog
from app.api.routers.agent_graph_mutations import AddToolRequest, GraphPatchRequest as AgentGraphPatchRequest, RemoveToolRequest, SetInstructionsRequest, SetModelRequest
from app.api.routers.knowledge_stores import CreateKnowledgeStoreRequest, UpdateKnowledgeStoreRequest
from app.api.routers.models import CreateModelRequest, UpdateModelRequest
from app.api.routers.orchestration_internal import CancelSubtreeRequest, EvaluateAndReplanRequest, JoinRequest
from app.api.routers.rag_graph_mutations import AttachKnowledgeStoreRequest, GraphPatchRequest as RagGraphPatchRequest, SetPipelineNodeConfigRequest
from app.api.routers.rag_operator_contracts import OperatorSchemaRequest
from app.api.routers.rag_pipelines import CreateJobRequest, CreatePipelineRequest, UpdatePipelineRequest, compile_pipeline, create_pipeline_job, get_executable_pipeline, get_executable_pipeline_input_schema, get_pipeline_context, get_pipeline_job
from app.api.routers.settings import CreateCredentialRequest, UpdateCredentialRequest, list_credentials, create_credential, update_credential
from app.api.routers.tools import CreateToolRequest, UpdateToolRequest
from app.core.scope_registry import get_required_scopes_for_action
from app.db.postgres.engine import sessionmaker as get_session
from app.db.postgres.models.registry import ToolStatus
from app.services.agent_graph_mutation_service import AgentGraphMutationService
from app.services.orchestration_policy_service import ORCHESTRATION_SURFACE_OPTION_B, is_orchestration_surface_enabled
from app.services.platform_architect_contracts import PLATFORM_ARCHITECT_DOMAIN_TOOLS
from app.services.rag_graph_mutation_service import RagGraphMutationService
from app.services.thread_service import ThreadService
from app.services.tool_function_registry import register_tool_function


PLATFORM_NATIVE_FUNCTIONS: dict[str, str] = {
    "platform-rag": "platform_native_platform_rag",
    "platform-agents": "platform_native_platform_agents",
    "platform-assets": "platform_native_platform_assets",
    "platform-governance": "platform_native_platform_governance",
}

ACTION_ALIASES = {
    "fetch_catalog": "catalog.list_capabilities",
    "create_agent": "agents.create",
    "update_agent": "agents.update",
    "run_agent_tests": "agents.run_tests",
    "create_pipeline": "rag.create_visual_pipeline",
    "update_pipeline": "rag.update_visual_pipeline",
    "compile_pipeline": "rag.compile_visual_pipeline",
    "publish_artifact": "artifacts.publish",
    "create_tool": "tools.create_or_update",
    "run_agent": "agents.execute",
    "run_tests": "agents.run_tests",
}

PUBLISH_ACTIONS = {
    "agents.publish",
    "tools.publish",
    "artifacts.publish",
}


def _normalize_payload(payload: Any) -> dict[str, Any]:
    return dict(payload) if isinstance(payload, dict) else {}


def _parse_uuid(raw: Any) -> UUID | None:
    if raw in (None, ""):
        return None
    try:
        return UUID(str(raw))
    except Exception:
        return None


def _request_stub() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/internal/platform-tools", "headers": []})


def _canonicalize_action(action: str) -> str:
    return ACTION_ALIASES.get(action, action)


def _resolve_tool_slug(payload: dict[str, Any]) -> str | None:
    raw = payload.get("tool_slug")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    runtime = payload.get("__tool_runtime_context__")
    if isinstance(runtime, dict):
        candidate = runtime.get("tool_slug")
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


def _extract_meta(inputs: dict[str, Any], payload: dict[str, Any], tool_slug: str | None) -> dict[str, Any]:
    request_metadata = payload.get("request_metadata") if isinstance(payload.get("request_metadata"), dict) else {}
    idempotency_key = payload.get("idempotency_key") or inputs.get("idempotency_key")
    trace_id = request_metadata.get("trace_id") or payload.get("trace_id")
    request_id = request_metadata.get("request_id") or payload.get("request_id")
    return {
        "trace_id": str(trace_id) if trace_id is not None else None,
        "request_id": str(request_id) if request_id is not None else None,
        "idempotency_key": str(idempotency_key) if idempotency_key else None,
        "idempotency_provided": bool(idempotency_key),
        "tool_slug": tool_slug,
    }


def _resolve_runtime_tenant_id(runtime_context: dict[str, Any]) -> str | None:
    tenant_id = runtime_context.get("tenant_id")
    return str(tenant_id) if tenant_id is not None else None


def _resolve_explicit_tenant_id(inputs: dict[str, Any], payload: dict[str, Any]) -> str | None:
    tenant_id = payload.get("tenant_id") or inputs.get("tenant_id")
    return str(tenant_id) if tenant_id is not None else None


def _validate_tenant_override(inputs: dict[str, Any], payload: dict[str, Any], runtime_context: dict[str, Any]) -> dict[str, Any] | None:
    runtime_tenant_id = _resolve_runtime_tenant_id(runtime_context)
    explicit_tenant_id = _resolve_explicit_tenant_id(inputs, payload)
    if not runtime_tenant_id or not explicit_tenant_id or runtime_tenant_id == explicit_tenant_id:
        return None
    return {
        "error": "tenant_override_denied",
        "code": "TENANT_MISMATCH",
        "message": "Tenant override is not allowed; runtime tenant context is authoritative.",
        "http_status": 403,
        "retryable": False,
        "runtime_tenant_id": runtime_tenant_id,
        "requested_tenant_id": explicit_tenant_id,
    }


def _required_scopes(action: str) -> list[str]:
    return sorted(set(get_required_scopes_for_action(action)))


def _has_explicit_publish_intent(inputs: dict[str, Any], payload: dict[str, Any]) -> bool:
    candidates = [
        payload.get("allow_publish"),
        payload.get("publish_intent"),
        inputs.get("allow_publish"),
        inputs.get("publish_intent"),
    ]
    objective_flags = payload.get("objective_flags") if isinstance(payload.get("objective_flags"), dict) else {}
    candidates.append(objective_flags.get("allow_publish"))
    for candidate in candidates:
        if isinstance(candidate, bool):
            return candidate
        if isinstance(candidate, str) and candidate.strip().lower() in {"1", "true", "yes", "publish"}:
            return True
    return False


def _ensure_allowed_action(tool_slug: str, action: str) -> None:
    allowed = PLATFORM_ARCHITECT_DOMAIN_TOOLS.get(tool_slug, {}).get("actions", {})
    if action in allowed:
        return
    raise HTTPException(
        status_code=403,
        detail={
            "code": "SCOPE_DENIED",
            "message": f"Action '{action}' is not allowed by tool '{tool_slug}'.",
            "action": action,
            "tool_slug": tool_slug,
        },
    )


def _serialize_value(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize_value(val) for key, val in value.items()}
    return value


def _http_error_payload(exc: HTTPException) -> dict[str, Any]:
    detail = exc.detail
    if isinstance(detail, dict):
        payload = dict(detail)
        payload.setdefault("message", str(payload.get("detail") or payload.get("message") or "Request failed"))
        payload.setdefault("code", "HTTP_ERROR")
    else:
        payload = {"message": str(detail or "Request failed"), "code": "HTTP_ERROR"}
    payload.setdefault("http_status", exc.status_code)
    payload.setdefault("retryable", False)
    payload.setdefault("error", str(payload.get("code", "HTTP_ERROR")).lower())
    return payload


def _validation_error_payload(exc: ValidationError) -> dict[str, Any]:
    return {
        "error": "validation_error",
        "code": "VALIDATION_ERROR",
        "message": "Validation failed",
        "http_status": 422,
        "retryable": False,
        "details": exc.errors(),
    }


def _finalize_success(*, action: str, dry_run: bool, result: Any, inputs: dict[str, Any], payload: dict[str, Any], tool_slug: str | None) -> dict[str, Any]:
    output = {
        "result": _serialize_value(result),
        "errors": [],
        "action": action,
        "dry_run": dry_run,
        "meta": _extract_meta(inputs=inputs, payload=payload, tool_slug=tool_slug),
    }
    return output


def _finalize_error(*, action: str, dry_run: bool, error: dict[str, Any], inputs: dict[str, Any], payload: dict[str, Any], tool_slug: str | None) -> dict[str, Any]:
    output = {
        "result": {
            "status": "validation_error" if int(error.get("http_status") or 500) < 500 else "failed",
            "message": error.get("message"),
        },
        "errors": [error],
        "action": action,
        "dry_run": dry_run,
        "meta": _extract_meta(inputs=inputs, payload=payload, tool_slug=tool_slug),
    }
    return output


class NativePlatformToolRuntime:
    def __init__(self, db: AsyncSession, payload: dict[str, Any]):
        self.db = db
        self.raw_payload = payload
        self.runtime_context = dict(payload.get("__tool_runtime_context__")) if isinstance(payload.get("__tool_runtime_context__"), dict) else {}
        self.inputs = {key: value for key, value in payload.items() if key != "__tool_runtime_context__"}
        self.payload = dict(self.inputs.get("payload")) if isinstance(self.inputs.get("payload"), dict) else {}
        self.tool_slug = _resolve_tool_slug(payload)
        self.dry_run = bool(self.inputs.get("dry_run") or self.payload.get("dry_run", False))
        self.action = _canonicalize_action(str(self.inputs.get("action") or "").strip()) if self.inputs.get("action") else "noop"
        self._principal: dict[str, Any] | None = None

    async def resolve_principal(self) -> dict[str, Any]:
        if self._principal is not None:
            return self._principal
        architect_scopes = self.runtime_context.get("architect_effective_scopes")
        architect_mode = self.runtime_context.get("architect_mode")
        token = self.runtime_context.get("token") or self.runtime_context.get("auth_token")
        if isinstance(token, str) and token.strip():
            try:
                self._principal = await get_current_principal(token=token.strip(), db=self.db)
                if isinstance(architect_scopes, list):
                    self._principal = {
                        **self._principal,
                        "scopes": [str(scope) for scope in architect_scopes if str(scope).strip()],
                        "architect_mode": architect_mode,
                    }
                return self._principal
            except Exception:
                pass

        tenant_id = _resolve_runtime_tenant_id(self.runtime_context) or _resolve_explicit_tenant_id(self.inputs, self.payload)
        scopes = (
            [str(scope) for scope in architect_scopes if str(scope).strip()]
            if isinstance(architect_scopes, list)
            else list(self.runtime_context.get("scopes") or ["*"])
        )
        user_id = self.runtime_context.get("user_id") or self.runtime_context.get("initiator_user_id")
        self._principal = {
            "type": "user",
            "tenant_id": str(tenant_id) if tenant_id else None,
            "user_id": str(user_id) if user_id else None,
            "user": None,
            "scopes": scopes,
            "auth_token": token,
            "architect_mode": architect_mode,
        }
        return self._principal

    async def build_agent_context(self) -> dict[str, Any]:
        principal = await self.resolve_principal()
        return {
            "user": principal.get("user"),
            "tenant_id": principal.get("tenant_id"),
            "auth_token": principal.get("auth_token"),
            "initiator_user_id": principal.get("initiator_user_id"),
            "scopes": principal.get("scopes", []),
            "architect_mode": principal.get("architect_mode"),
        }

    async def build_tools_context(self) -> dict[str, Any]:
        principal = await self.resolve_principal()
        tenant_id = principal.get("tenant_id")
        return {
            "tenant_id": str(tenant_id) if tenant_id else None,
            "tenant": SimpleNamespace(id=UUID(str(tenant_id))) if tenant_id else None,
            "user": principal.get("user"),
            "is_service": False,
        }

    async def build_tenant_context(self) -> dict[str, Any]:
        principal = await self.resolve_principal()
        return {"tenant_id": str(principal.get("tenant_id")) if principal.get("tenant_id") else None}

    async def validate(self) -> None:
        if not self.tool_slug:
            raise HTTPException(status_code=400, detail={"code": "MISSING_TOOL_SLUG", "message": "Missing tool slug"})
        if self.action == "noop":
            raise HTTPException(status_code=422, detail={"code": "MISSING_REQUIRED_FIELD", "message": "Missing required field: action"})
        _ensure_allowed_action(self.tool_slug, self.action)
        tenant_error = _validate_tenant_override(self.inputs, self.payload, self.runtime_context)
        if tenant_error:
            raise HTTPException(status_code=403, detail=tenant_error)
        principal = await self.resolve_principal()
        required_scopes = _required_scopes(self.action)
        scopes = set(principal.get("scopes") or [])
        if required_scopes and "*" not in scopes and any(scope not in scopes for scope in required_scopes):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "SCOPE_DENIED",
                    "message": f"Action '{self.action}' requires scopes: {', '.join(required_scopes)}",
                    "required_scopes": required_scopes,
                },
            )
        if self.action in PUBLISH_ACTIONS and not _has_explicit_publish_intent(self.inputs, self.payload):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "DRAFT_FIRST_POLICY_DENIED",
                    "message": f"Action '{self.action}' requires explicit publish intent.",
                },
            )
        if self.action.startswith("orchestration."):
            tenant_id = principal.get("tenant_id")
            if not is_orchestration_surface_enabled(surface=ORCHESTRATION_SURFACE_OPTION_B, tenant_id=tenant_id):
                raise HTTPException(
                    status_code=403,
                    detail={
                        "code": "FEATURE_DISABLED",
                        "message": "Runtime orchestration primitives are disabled by feature flag for this tenant",
                    },
                )

    async def dispatch(self) -> dict[str, Any]:
        try:
            await self.validate()
            result = await _ACTION_HANDLERS[self.action](self)
            return _finalize_success(
                action=self.action,
                dry_run=self.dry_run,
                result=result,
                inputs=self.inputs,
                payload=self.payload,
                tool_slug=self.tool_slug,
            )
        except ValidationError as exc:
            return _finalize_error(action=self.action, dry_run=self.dry_run, error=_validation_error_payload(exc), inputs=self.inputs, payload=self.payload, tool_slug=self.tool_slug)
        except HTTPException as exc:
            return _finalize_error(action=self.action, dry_run=self.dry_run, error=_http_error_payload(exc), inputs=self.inputs, payload=self.payload, tool_slug=self.tool_slug)


def _pipeline_shell_graph() -> dict[str, Any]:
    return {
        "nodes": [
            {"id": "query_input_1", "category": "input", "operator": "query_input", "position": {"x": 0, "y": 0}, "config": {}},
            {"id": "retrieval_result_1", "category": "output", "operator": "retrieval_result", "position": {"x": 280, "y": 0}, "config": {}},
        ],
        "edges": [{"id": "edge_query_to_result", "source": "query_input_1", "target": "retrieval_result_1"}],
    }


def _normalize_graph_definition(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes = list(payload.get("nodes") or [])
    edges = list(payload.get("edges") or [])
    graph_definition = payload.get("graph_definition")
    if isinstance(graph_definition, dict):
        if not nodes and isinstance(graph_definition.get("nodes"), list):
            nodes = list(graph_definition.get("nodes") or [])
        if not edges and isinstance(graph_definition.get("edges"), list):
            edges = list(graph_definition.get("edges") or [])
    return nodes, edges


async def _rag_list_visual_pipelines(rt: NativePlatformToolRuntime) -> Any:
    principal = await rt.resolve_principal()
    return await rag_pipelines.list_visual_pipelines(
        tenant_slug=rt.payload.get("tenant_slug"),
        current_user=principal.get("user"),
        db=rt.db,
    )


async def _rag_operators_catalog(rt: NativePlatformToolRuntime) -> Any:
    principal = await rt.resolve_principal()
    raw = await rag_pipelines.list_operator_specs(
        tenant_slug=rt.payload.get("tenant_slug"),
        current_user=principal.get("user"),
        db=rt.db,
    )
    operators: list[dict[str, Any]] = []
    if isinstance(raw, dict):
        for item in raw.values():
            if isinstance(item, dict):
                operators.append(item)
    return {"operators": operators, "categories": raw}


async def _rag_operators_schema(rt: NativePlatformToolRuntime) -> Any:
    principal = await rt.resolve_principal()
    request = OperatorSchemaRequest(operator_ids=list(rt.payload.get("operator_ids") or []))
    return await rag_operator_contracts.get_operator_schemas(
        request=request,
        tenant_slug=rt.payload.get("tenant_slug"),
        context=principal,
        _={},
        db=rt.db,
    )


async def _rag_create_pipeline_shell(rt: NativePlatformToolRuntime) -> Any:
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "name": str(rt.payload.get("name") or "")}
    nodes, edges = _normalize_graph_definition(_pipeline_shell_graph())
    principal = await rt.resolve_principal()
    request = CreatePipelineRequest(
        name=str(rt.payload.get("name") or ""),
        description=rt.payload.get("description"),
        pipeline_type=rt.payload.get("pipeline_type") or "retrieval",
        nodes=nodes,
        edges=edges,
    )
    return await rag_pipelines.create_visual_pipeline(
        request=request,
        http_request=_request_stub(),
        tenant_slug=rt.payload.get("tenant_slug"),
        context=principal,
        _={},
        db=rt.db,
    )


async def _rag_create_visual_pipeline(rt: NativePlatformToolRuntime) -> Any:
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "name": str(rt.payload.get("name") or "")}
    nodes, edges = _normalize_graph_definition(rt.payload)
    principal = await rt.resolve_principal()
    request = CreatePipelineRequest(
        name=str(rt.payload.get("name") or ""),
        description=rt.payload.get("description"),
        pipeline_type=rt.payload.get("pipeline_type") or "retrieval",
        nodes=nodes,
        edges=edges,
    )
    return await rag_pipelines.create_visual_pipeline(request=request, http_request=_request_stub(), tenant_slug=rt.payload.get("tenant_slug"), context=principal, _={}, db=rt.db)


async def _rag_update_visual_pipeline(rt: NativePlatformToolRuntime) -> Any:
    pipeline_id = _parse_uuid(rt.payload.get("pipeline_id") or rt.payload.get("id"))
    if pipeline_id is None:
        raise HTTPException(status_code=422, detail={"code": "MISSING_REQUIRED_FIELD", "message": "pipeline_id is required"})
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "pipeline_id": str(pipeline_id)}
    patch = dict(rt.payload.get("patch")) if isinstance(rt.payload.get("patch"), dict) else {}
    nodes, edges = _normalize_graph_definition(patch)
    principal = await rt.resolve_principal()
    request = UpdatePipelineRequest(
        name=patch.get("name"),
        description=patch.get("description"),
        pipeline_type=patch.get("pipeline_type"),
        nodes=nodes or None,
        edges=edges or None,
    )
    return await rag_pipelines.update_visual_pipeline(pipeline_id=pipeline_id, request=request, http_request=_request_stub(), tenant_slug=rt.payload.get("tenant_slug"), context=principal, _={}, db=rt.db)


async def _rag_graph_get(rt: NativePlatformToolRuntime) -> Any:
    pipeline_id = _parse_uuid(rt.payload.get("pipeline_id") or rt.payload.get("id"))
    if pipeline_id is None:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    principal = await rt.resolve_principal()
    tenant, _user, _db = await get_pipeline_context(rt.payload.get("tenant_slug"), current_user=principal.get("user"), db=rt.db, context=principal)
    service = RagGraphMutationService(rt.db, tenant_id=tenant.id)
    return await service.get_graph(pipeline_id)


async def _rag_graph_validate_patch(rt: NativePlatformToolRuntime) -> Any:
    pipeline_id = _parse_uuid(rt.payload.get("pipeline_id") or rt.payload.get("id"))
    if pipeline_id is None:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    principal = await rt.resolve_principal()
    tenant, _user, _db = await get_pipeline_context(rt.payload.get("tenant_slug"), current_user=principal.get("user"), db=rt.db, context=principal)
    service = RagGraphMutationService(rt.db, tenant_id=tenant.id)
    request = RagGraphPatchRequest(operations=list(rt.payload.get("operations") or []))
    return await service.validate_patch(pipeline_id, request.operations)


async def _rag_graph_apply_patch(rt: NativePlatformToolRuntime) -> Any:
    pipeline_id = _parse_uuid(rt.payload.get("pipeline_id") or rt.payload.get("id"))
    if pipeline_id is None:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "pipeline_id": str(pipeline_id)}
    principal = await rt.resolve_principal()
    tenant, _user, _db = await get_pipeline_context(rt.payload.get("tenant_slug"), current_user=principal.get("user"), db=rt.db, context=principal)
    service = RagGraphMutationService(rt.db, tenant_id=tenant.id)
    request = RagGraphPatchRequest(operations=list(rt.payload.get("operations") or []))
    return await service.apply_patch(pipeline_id, request.operations)


async def _rag_graph_attach_knowledge_store(rt: NativePlatformToolRuntime) -> Any:
    pipeline_id = _parse_uuid(rt.payload.get("pipeline_id") or rt.payload.get("id"))
    if pipeline_id is None:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "pipeline_id": str(pipeline_id)}
    principal = await rt.resolve_principal()
    tenant, _user, _db = await get_pipeline_context(rt.payload.get("tenant_slug"), current_user=principal.get("user"), db=rt.db, context=principal)
    service = RagGraphMutationService(rt.db, tenant_id=tenant.id)
    request = AttachKnowledgeStoreRequest(node_id=str(rt.payload.get("node_id") or ""), knowledge_store_id=str(rt.payload.get("knowledge_store_id") or ""))
    return await service.attach_knowledge_store_to_node(pipeline_id, node_id=request.node_id, knowledge_store_id=request.knowledge_store_id)


async def _rag_graph_set_node_config(rt: NativePlatformToolRuntime) -> Any:
    pipeline_id = _parse_uuid(rt.payload.get("pipeline_id") or rt.payload.get("id"))
    if pipeline_id is None:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "pipeline_id": str(pipeline_id)}
    principal = await rt.resolve_principal()
    tenant, _user, _db = await get_pipeline_context(rt.payload.get("tenant_slug"), current_user=principal.get("user"), db=rt.db, context=principal)
    service = RagGraphMutationService(rt.db, tenant_id=tenant.id)
    request = SetPipelineNodeConfigRequest(node_id=str(rt.payload.get("node_id") or ""), path=str(rt.payload.get("path") or ""), value=rt.payload.get("value"))
    return await service.set_pipeline_node_config(pipeline_id, node_id=request.node_id, path=request.path, value=request.value)


async def _rag_compile_visual_pipeline(rt: NativePlatformToolRuntime) -> Any:
    pipeline_id = _parse_uuid(rt.payload.get("pipeline_id") or rt.payload.get("id"))
    if pipeline_id is None:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "pipeline_id": str(pipeline_id)}
    principal = await rt.resolve_principal()
    return await compile_pipeline(pipeline_id=pipeline_id, http_request=_request_stub(), tenant_slug=rt.payload.get("tenant_slug"), context=principal, _={}, db=rt.db)


async def _rag_get_executable_pipeline(rt: NativePlatformToolRuntime) -> Any:
    pipeline_id = _parse_uuid(rt.payload.get("pipeline_id") or rt.payload.get("id"))
    if pipeline_id is None:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    principal = await rt.resolve_principal()
    return await get_executable_pipeline(pipeline_id=pipeline_id, tenant_slug=rt.payload.get("tenant_slug"), context=principal, _={}, db=rt.db)


async def _rag_get_executable_input_schema(rt: NativePlatformToolRuntime) -> Any:
    pipeline_id = _parse_uuid(rt.payload.get("pipeline_id") or rt.payload.get("id"))
    if pipeline_id is None:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    principal = await rt.resolve_principal()
    return await get_executable_pipeline_input_schema(pipeline_id=pipeline_id, tenant_slug=rt.payload.get("tenant_slug"), context=principal, _={}, db=rt.db)


async def _rag_create_job(rt: NativePlatformToolRuntime) -> Any:
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True}
    principal = await rt.resolve_principal()
    request = CreateJobRequest(
        executable_pipeline_id=_parse_uuid(rt.payload.get("executable_pipeline_id") or rt.payload.get("pipeline_id") or rt.payload.get("id")),
        input_params=rt.payload.get("input_params") if isinstance(rt.payload.get("input_params"), dict) else {},
    )
    return await create_pipeline_job(request=request, http_request=_request_stub(), background_tasks=SimpleNamespace(add_task=lambda *args, **kwargs: None), tenant_slug=rt.payload.get("tenant_slug"), current_user=principal.get("user"), db=rt.db)


async def _rag_get_job(rt: NativePlatformToolRuntime) -> Any:
    job_id = _parse_uuid(rt.payload.get("job_id") or rt.payload.get("id"))
    if job_id is None:
        raise HTTPException(status_code=404, detail="Job not found")
    principal = await rt.resolve_principal()
    return await get_pipeline_job(job_id=job_id, tenant_slug=rt.payload.get("tenant_slug"), current_user=principal.get("user"), db=rt.db)


async def _agents_list(rt: NativePlatformToolRuntime) -> Any:
    context = await rt.build_agent_context()
    return await agents.list_agents(status=rt.payload.get("status"), skip=int(rt.payload.get("skip") or 0), limit=int(rt.payload.get("limit") or 50), compact=bool(rt.payload.get("compact", False)), context=context, db=rt.db)


async def _agents_get(rt: NativePlatformToolRuntime) -> Any:
    agent_id = _parse_uuid(rt.payload.get("agent_id") or rt.payload.get("id"))
    if agent_id is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    context = await rt.build_agent_context()
    return await agents.get_agent(agent_id=agent_id, context=context, db=rt.db)


async def _agents_create_shell(rt: NativePlatformToolRuntime) -> Any:
    graph_definition = {"nodes": [{"id": "start", "type": "start", "position": {"x": 0, "y": 0}, "config": {}}, {"id": "end", "type": "end", "position": {"x": 240, "y": 0}, "config": {}}], "edges": [{"id": "e_start_end", "source": "start", "target": "end", "type": "control"}], "spec_version": "2.0"}
    payload = dict(rt.payload)
    payload["graph_definition"] = graph_definition
    return await _agents_create_or_update(rt, create_only=True, override_payload=payload)


async def _agents_create_or_update(rt: NativePlatformToolRuntime, *, create_only: bool = False, override_payload: dict[str, Any] | None = None) -> Any:
    payload = override_payload or rt.payload
    context = await rt.build_agent_context()
    graph_definition = payload.get("graph_definition") if isinstance(payload.get("graph_definition"), dict) else {}
    if rt.dry_run:
        skipped = {"status": "skipped", "dry_run": True}
        if payload.get("agent_id") or payload.get("id"):
            skipped["agent_id"] = str(payload.get("agent_id") or payload.get("id"))
        else:
            skipped["name"] = payload.get("name")
        return skipped
    if create_only or not (payload.get("agent_id") or payload.get("id")):
        request = CreateAgentRequest(name=str(payload.get("name") or ""), slug=str(payload.get("slug") or ""), description=payload.get("description"), graph_definition=graph_definition, memory_config=payload.get("memory_config"), execution_constraints=payload.get("execution_constraints"))
        return await agents.create_agent(request=request, _={}, context=context, db=rt.db)
    agent_id = _parse_uuid(payload.get("agent_id") or payload.get("id"))
    if agent_id is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    patch = dict(payload.get("patch")) if isinstance(payload.get("patch"), dict) else dict(payload)
    request = UpdateAgentRequest(name=patch.get("name"), description=patch.get("description"), graph_definition=patch.get("graph_definition"), memory_config=patch.get("memory_config"), execution_constraints=patch.get("execution_constraints"))
    return await agents.update_agent(agent_id=agent_id, request=request, _={}, context=context, db=rt.db)


async def _agents_graph_get(rt: NativePlatformToolRuntime) -> Any:
    agent_id = _parse_uuid(rt.payload.get("agent_id") or rt.payload.get("id"))
    if agent_id is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    context = await rt.build_agent_context()
    service = AgentGraphMutationService(db=rt.db, tenant_id=context["tenant_id"])
    return await service.get_graph(agent_id)


async def _agents_graph_validate_patch(rt: NativePlatformToolRuntime) -> Any:
    agent_id = _parse_uuid(rt.payload.get("agent_id") or rt.payload.get("id"))
    if agent_id is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    context = await rt.build_agent_context()
    service = AgentGraphMutationService(db=rt.db, tenant_id=context["tenant_id"])
    request = AgentGraphPatchRequest(operations=list(rt.payload.get("operations") or []))
    return await service.validate_patch(agent_id, request.operations)


async def _agents_graph_apply_patch(rt: NativePlatformToolRuntime) -> Any:
    agent_id = _parse_uuid(rt.payload.get("agent_id") or rt.payload.get("id"))
    if agent_id is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "agent_id": str(agent_id)}
    context = await rt.build_agent_context()
    service = AgentGraphMutationService(db=rt.db, tenant_id=context["tenant_id"])
    request = AgentGraphPatchRequest(operations=list(rt.payload.get("operations") or []))
    user_id = context["user"].id if context.get("user") else None
    return await service.apply_patch(agent_id, request.operations, user_id=user_id)


async def _agents_graph_add_tool(rt: NativePlatformToolRuntime) -> Any:
    agent_id = _parse_uuid(rt.payload.get("agent_id") or rt.payload.get("id"))
    context = await rt.build_agent_context()
    service = AgentGraphMutationService(db=rt.db, tenant_id=context["tenant_id"])
    request = AddToolRequest(node_id=str(rt.payload.get("node_id") or ""), tool_id=str(rt.payload.get("tool_id") or ""))
    user_id = context["user"].id if context.get("user") else None
    return await service.add_tool_to_agent_node(agent_id, node_id=request.node_id, tool_id=request.tool_id, user_id=user_id)


async def _agents_graph_remove_tool(rt: NativePlatformToolRuntime) -> Any:
    agent_id = _parse_uuid(rt.payload.get("agent_id") or rt.payload.get("id"))
    context = await rt.build_agent_context()
    service = AgentGraphMutationService(db=rt.db, tenant_id=context["tenant_id"])
    request = RemoveToolRequest(node_id=str(rt.payload.get("node_id") or ""), tool_id=str(rt.payload.get("tool_id") or ""))
    user_id = context["user"].id if context.get("user") else None
    return await service.remove_tool_from_agent_node(agent_id, node_id=request.node_id, tool_id=request.tool_id, user_id=user_id)


async def _agents_graph_set_model(rt: NativePlatformToolRuntime) -> Any:
    agent_id = _parse_uuid(rt.payload.get("agent_id") or rt.payload.get("id"))
    context = await rt.build_agent_context()
    service = AgentGraphMutationService(db=rt.db, tenant_id=context["tenant_id"])
    request = SetModelRequest(node_id=str(rt.payload.get("node_id") or ""), model_id=str(rt.payload.get("model_id") or ""))
    user_id = context["user"].id if context.get("user") else None
    return await service.set_agent_model(agent_id, node_id=request.node_id, model_id=request.model_id, user_id=user_id)


async def _agents_graph_set_instructions(rt: NativePlatformToolRuntime) -> Any:
    agent_id = _parse_uuid(rt.payload.get("agent_id") or rt.payload.get("id"))
    context = await rt.build_agent_context()
    service = AgentGraphMutationService(db=rt.db, tenant_id=context["tenant_id"])
    request = SetInstructionsRequest(node_id=str(rt.payload.get("node_id") or ""), instructions=str(rt.payload.get("instructions") or ""))
    user_id = context["user"].id if context.get("user") else None
    return await service.set_agent_instructions(agent_id, node_id=request.node_id, instructions=request.instructions, user_id=user_id)


async def _agents_publish(rt: NativePlatformToolRuntime) -> Any:
    agent_id = _parse_uuid(rt.payload.get("agent_id") or rt.payload.get("id"))
    context = await rt.build_agent_context()
    principal = await rt.resolve_principal()
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "agent_id": str(agent_id)}
    return await agents.publish_agent(agent_id=agent_id, principal=principal, _={}, context=context, db=rt.db)


async def _agents_validate(rt: NativePlatformToolRuntime) -> Any:
    agent_id = _parse_uuid(rt.payload.get("agent_id") or rt.payload.get("id"))
    context = await rt.build_agent_context()
    return await agents.validate_agent(agent_id=agent_id, _={}, context=context, db=rt.db)


async def _agents_nodes_catalog(rt: NativePlatformToolRuntime) -> Any:
    context = await rt.build_agent_context()
    return await list_node_catalog(_={}, context=context, db=rt.db)


async def _agents_nodes_schema(rt: NativePlatformToolRuntime) -> Any:
    context = await rt.build_agent_context()
    request = NodeSchemaRequest(node_types=list(rt.payload.get("node_types") or []))
    return await get_node_schemas(request=request, _={}, context=context, db=rt.db)


async def _agents_nodes_validate(rt: NativePlatformToolRuntime) -> Any:
    context = await rt.build_agent_context()
    agent_id = _parse_uuid(rt.payload.get("agent_id") or rt.payload.get("id"))
    return await agents.validate_agent(agent_id=agent_id, _={}, context=context, db=rt.db)


async def _agents_execute(rt: NativePlatformToolRuntime) -> Any:
    agent_id = _parse_uuid(rt.payload.get("agent_id") or rt.payload.get("id"))
    context = await rt.build_agent_context()
    request = ExecuteAgentRequest(input=rt.payload.get("input"), messages=list(rt.payload.get("messages") or []), context=rt.payload.get("context") if isinstance(rt.payload.get("context"), dict) else {}, thread_id=_parse_uuid(rt.payload.get("thread_id")))
    return await agents.start_run_v2(agent_id=agent_id, request=request, _={}, context=context, db=rt.db)


async def _agents_start_run(rt: NativePlatformToolRuntime) -> Any:
    return await _agents_execute(rt)


async def _agents_get_run(rt: NativePlatformToolRuntime) -> Any:
    run_id = _parse_uuid(rt.payload.get("run_id") or rt.payload.get("id"))
    context = await rt.build_agent_context()
    return await agents.get_run_status(run_id=run_id, include_tree=bool(rt.payload.get("include_tree", False)), _={}, context=context, db=rt.db)


async def _artifacts_list(rt: NativePlatformToolRuntime) -> Any:
    principal = await rt.resolve_principal()
    artifact_ctx = await artifacts.get_artifact_context(tenant_slug=rt.payload.get("tenant_slug"), context=principal, db=rt.db)
    return await artifacts.list_artifacts(tenant_slug=rt.payload.get("tenant_slug"), artifact_ctx=artifact_ctx)


async def _artifacts_get(rt: NativePlatformToolRuntime) -> Any:
    principal = await rt.resolve_principal()
    artifact_ctx = await artifacts.get_artifact_context(tenant_slug=rt.payload.get("tenant_slug"), context=principal, db=rt.db)
    artifact_id = str(rt.payload.get("artifact_id") or rt.payload.get("id") or "")
    return await artifacts.get_artifact(artifact_id=artifact_id, tenant_slug=rt.payload.get("tenant_slug"), artifact_ctx=artifact_ctx)


async def _artifacts_create(rt: NativePlatformToolRuntime) -> Any:
    principal = await rt.resolve_principal()
    artifact_ctx = await artifacts.get_artifact_context(tenant_slug=rt.payload.get("tenant_slug"), context=principal, db=rt.db)
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "display_name": str(rt.payload.get("display_name") or "")}
    request = ArtifactCreate(
        display_name=str(rt.payload.get("display_name") or ""),
        description=rt.payload.get("description"),
        kind=rt.payload.get("kind"),
        runtime=rt.payload.get("runtime") if isinstance(rt.payload.get("runtime"), dict) else {},
        config_schema=rt.payload.get("config_schema") if isinstance(rt.payload.get("config_schema"), dict) else {},
        capabilities=rt.payload.get("capabilities") if isinstance(rt.payload.get("capabilities"), dict) else {},
        agent_contract=rt.payload.get("agent_contract") if isinstance(rt.payload.get("agent_contract"), dict) else None,
        rag_contract=rt.payload.get("rag_contract") if isinstance(rt.payload.get("rag_contract"), dict) else None,
        tool_contract=rt.payload.get("tool_contract") if isinstance(rt.payload.get("tool_contract"), dict) else None,
    )
    return await artifacts.create_artifact(request=request, artifact_ctx=artifact_ctx)


async def _artifacts_update(rt: NativePlatformToolRuntime) -> Any:
    principal = await rt.resolve_principal()
    artifact_ctx = await artifacts.get_artifact_context(tenant_slug=rt.payload.get("tenant_slug"), context=principal, db=rt.db)
    artifact_id = str(rt.payload.get("artifact_id") or rt.payload.get("id") or "")
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "artifact_id": artifact_id}
    patch = dict(rt.payload.get("patch")) if isinstance(rt.payload.get("patch"), dict) else {}
    request = ArtifactUpdate(
        display_name=patch.get("display_name"),
        description=patch.get("description"),
        config_schema=patch.get("config_schema"),
        runtime=patch.get("runtime"),
        capabilities=patch.get("capabilities"),
        agent_contract=patch.get("agent_contract"),
        rag_contract=patch.get("rag_contract"),
        tool_contract=patch.get("tool_contract"),
    )
    return await artifacts.update_artifact(artifact_id=artifact_id, request=request, artifact_ctx=artifact_ctx)


async def _artifacts_convert_kind(rt: NativePlatformToolRuntime) -> Any:
    principal = await rt.resolve_principal()
    artifact_ctx = await artifacts.get_artifact_context(tenant_slug=rt.payload.get("tenant_slug"), context=principal, db=rt.db)
    artifact_id = str(rt.payload.get("artifact_id") or rt.payload.get("id") or "")
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "artifact_id": artifact_id}
    request = ArtifactConvertKindRequest(kind=rt.payload.get("kind"))
    return await artifacts.convert_artifact_kind(artifact_id=artifact_id, request=request, artifact_ctx=artifact_ctx)


async def _artifacts_create_test_run(rt: NativePlatformToolRuntime) -> Any:
    principal = await rt.resolve_principal()
    artifact_ctx = await artifacts.get_artifact_context(tenant_slug=rt.payload.get("tenant_slug"), context=principal, db=rt.db)
    artifact_id = str(rt.payload.get("artifact_id") or rt.payload.get("id") or "")
    request = ArtifactTestRequest(input=rt.payload.get("input"))
    return await artifacts.create_artifact_test_run(artifact_id=artifact_id, request=request, artifact_ctx=artifact_ctx)


async def _artifacts_publish(rt: NativePlatformToolRuntime) -> Any:
    principal = await rt.resolve_principal()
    artifact_ctx = await artifacts.get_artifact_context(tenant_slug=rt.payload.get("tenant_slug"), context=principal, db=rt.db)
    artifact_id = str(rt.payload.get("artifact_id") or rt.payload.get("id") or "")
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "artifact_id": artifact_id}
    return await artifacts.publish_artifact(artifact_id=artifact_id, principal=principal, artifact_ctx=artifact_ctx)


async def _artifacts_delete(rt: NativePlatformToolRuntime) -> Any:
    principal = await rt.resolve_principal()
    artifact_ctx = await artifacts.get_artifact_context(tenant_slug=rt.payload.get("tenant_slug"), context=principal, db=rt.db)
    artifact_id = str(rt.payload.get("artifact_id") or rt.payload.get("id") or "")
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "artifact_id": artifact_id}
    return await artifacts.delete_artifact(artifact_id=artifact_id, principal=principal, artifact_ctx=artifact_ctx)


async def _tools_list(rt: NativePlatformToolRuntime) -> Any:
    tenant_ctx = await rt.build_tools_context()
    return await tools.list_tools(scope=rt.payload.get("scope"), is_active=rt.payload.get("is_active", True), status=rt.payload.get("status"), implementation_type=rt.payload.get("implementation_type"), tool_type=rt.payload.get("tool_type"), skip=int(rt.payload.get("skip") or 0), limit=int(rt.payload.get("limit") or 50), db=rt.db, tenant_ctx=tenant_ctx)


async def _tools_get(rt: NativePlatformToolRuntime) -> Any:
    tenant_ctx = await rt.build_tools_context()
    tool_id = _parse_uuid(rt.payload.get("tool_id") or rt.payload.get("id"))
    return await tools.get_tool(tool_id=tool_id, db=rt.db, tenant_ctx=tenant_ctx)


async def _tools_create_or_update(rt: NativePlatformToolRuntime) -> Any:
    tenant_ctx = await rt.build_tools_context()
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "name": rt.payload.get("name")}
    if rt.payload.get("tool_id") or rt.payload.get("id"):
        tool_id = _parse_uuid(rt.payload.get("tool_id") or rt.payload.get("id"))
        patch = dict(rt.payload.get("patch")) if isinstance(rt.payload.get("patch"), dict) else dict(rt.payload)
        request = UpdateToolRequest(**{key: value for key, value in patch.items() if key in UpdateToolRequest.model_fields})
        return await tools.update_tool(tool_id=tool_id, request=request, _={}, db=rt.db, tenant_ctx=tenant_ctx)
    request = CreateToolRequest(**{key: value for key, value in rt.payload.items() if key in CreateToolRequest.model_fields})
    return await tools.create_tool(request=request, _={}, db=rt.db, tenant_ctx=tenant_ctx)


async def _tools_publish(rt: NativePlatformToolRuntime) -> Any:
    tenant_ctx = await rt.build_tools_context()
    principal = await rt.resolve_principal()
    tool_id = _parse_uuid(rt.payload.get("tool_id") or rt.payload.get("id"))
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "tool_id": str(tool_id)}
    return await tools.publish_tool(tool_id=tool_id, principal=principal, _={}, db=rt.db, tenant_ctx=tenant_ctx)


async def _models_list(rt: NativePlatformToolRuntime) -> Any:
    tenant_ctx = await rt.build_tenant_context()
    principal = await rt.resolve_principal()
    return await models.list_models(capability_type=rt.payload.get("capability_type"), is_active=rt.payload.get("is_active", True), skip=int(rt.payload.get("skip") or 0), limit=int(rt.payload.get("limit") or 50), db=rt.db, tenant_ctx=tenant_ctx, _={}, principal=principal)


async def _models_create_or_update(rt: NativePlatformToolRuntime) -> Any:
    tenant_ctx = await rt.build_tenant_context()
    principal = await rt.resolve_principal()
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "name": rt.payload.get("name")}
    model_id = _parse_uuid(rt.payload.get("model_id") or rt.payload.get("id"))
    if model_id is not None:
        patch = dict(rt.payload.get("patch")) if isinstance(rt.payload.get("patch"), dict) else dict(rt.payload)
        request = UpdateModelRequest(**{key: value for key, value in patch.items() if key in UpdateModelRequest.model_fields})
        return await models.update_model(model_id=model_id, request=request, db=rt.db, tenant_ctx=tenant_ctx, _={}, principal=principal)
    request = CreateModelRequest(**{key: value for key, value in rt.payload.items() if key in CreateModelRequest.model_fields})
    return await models.create_model(request=request, db=rt.db, tenant_ctx=tenant_ctx, _={}, principal=principal)


async def _credentials_list(rt: NativePlatformToolRuntime) -> Any:
    tenant_ctx = await rt.build_tenant_context()
    principal = await rt.resolve_principal()
    return await list_credentials(category=rt.payload.get("category"), db=rt.db, tenant_ctx=tenant_ctx, current_user=principal.get("user"))


async def _credentials_create_or_update(rt: NativePlatformToolRuntime) -> Any:
    tenant_ctx = await rt.build_tenant_context()
    principal = await rt.resolve_principal()
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "display_name": rt.payload.get("display_name")}
    credential_id = _parse_uuid(rt.payload.get("credential_id") or rt.payload.get("id"))
    if credential_id is not None:
        patch = dict(rt.payload.get("patch")) if isinstance(rt.payload.get("patch"), dict) else dict(rt.payload)
        request = UpdateCredentialRequest(**{key: value for key, value in patch.items() if key in UpdateCredentialRequest.model_fields})
        return await update_credential(credential_id=credential_id, request=request, db=rt.db, tenant_ctx=tenant_ctx, current_user=principal.get("user"))
    request = CreateCredentialRequest(**{key: value for key, value in rt.payload.items() if key in CreateCredentialRequest.model_fields})
    return await create_credential(request=request, db=rt.db, tenant_ctx=tenant_ctx, current_user=principal.get("user"))


async def _knowledge_stores_list(rt: NativePlatformToolRuntime) -> Any:
    tenant_ctx = await rt.build_tenant_context()
    principal = await rt.resolve_principal()
    return await knowledge_stores.list_knowledge_stores(tenant_slug=rt.payload.get("tenant_slug"), db=rt.db, tenant_ctx=tenant_ctx, _={}, principal=principal)


async def _knowledge_stores_create_or_update(rt: NativePlatformToolRuntime) -> Any:
    tenant_ctx = await rt.build_tenant_context()
    principal = await rt.resolve_principal()
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "name": rt.payload.get("name")}
    store_id = _parse_uuid(rt.payload.get("store_id") or rt.payload.get("knowledge_store_id") or rt.payload.get("id"))
    if store_id is not None:
        patch = dict(rt.payload.get("patch")) if isinstance(rt.payload.get("patch"), dict) else dict(rt.payload)
        request = UpdateKnowledgeStoreRequest(**{key: value for key, value in patch.items() if key in UpdateKnowledgeStoreRequest.model_fields})
        return await knowledge_stores.update_knowledge_store(store_id=store_id, request=request, tenant_slug=rt.payload.get("tenant_slug"), db=rt.db, tenant_ctx=tenant_ctx, _={}, principal=principal)
    request = CreateKnowledgeStoreRequest(**{key: value for key, value in rt.payload.items() if key in CreateKnowledgeStoreRequest.model_fields})
    return await knowledge_stores.create_knowledge_store(request=request, tenant_slug=rt.payload.get("tenant_slug"), db=rt.db, tenant_ctx=tenant_ctx, _={}, principal=principal)


async def _orchestration_join(rt: NativePlatformToolRuntime) -> Any:
    principal = await rt.resolve_principal()
    request = JoinRequest(
        caller_run_id=_parse_uuid(rt.payload.get("caller_run_id")),
        orchestration_group_id=_parse_uuid(rt.payload.get("orchestration_group_id")),
        mode=rt.payload.get("mode"),
        quorum_threshold=rt.payload.get("quorum_threshold"),
        timeout_s=rt.payload.get("timeout_s"),
    )
    return await orchestration_internal.join(request=request, principal=principal, _={}, db=rt.db)


async def _orchestration_cancel_subtree(rt: NativePlatformToolRuntime) -> Any:
    principal = await rt.resolve_principal()
    request = CancelSubtreeRequest(
        caller_run_id=_parse_uuid(rt.payload.get("caller_run_id")),
        run_id=_parse_uuid(rt.payload.get("run_id")),
        include_root=bool(rt.payload.get("include_root", True)),
        reason=rt.payload.get("reason"),
    )
    return await orchestration_internal.cancel_subtree(request=request, principal=principal, _={}, db=rt.db)


async def _orchestration_evaluate_and_replan(rt: NativePlatformToolRuntime) -> Any:
    principal = await rt.resolve_principal()
    request = EvaluateAndReplanRequest(caller_run_id=_parse_uuid(rt.payload.get("caller_run_id")), run_id=_parse_uuid(rt.payload.get("run_id")))
    return await orchestration_internal.evaluate_and_replan(request=request, principal=principal, _={}, db=rt.db)


async def _orchestration_query_tree(rt: NativePlatformToolRuntime) -> Any:
    principal = await rt.resolve_principal()
    run_id = _parse_uuid(rt.payload.get("run_id"))
    return await orchestration_internal.query_tree(run_id=run_id, principal=principal, _={}, db=rt.db)


_ACTION_HANDLERS: dict[str, Callable[[NativePlatformToolRuntime], Awaitable[Any]]] = {
    "rag.list_visual_pipelines": _rag_list_visual_pipelines,
    "rag.operators.catalog": _rag_operators_catalog,
    "rag.operators.schema": _rag_operators_schema,
    "rag.create_pipeline_shell": _rag_create_pipeline_shell,
    "rag.create_visual_pipeline": _rag_create_visual_pipeline,
    "rag.update_visual_pipeline": _rag_update_visual_pipeline,
    "rag.graph.get": _rag_graph_get,
    "rag.graph.validate_patch": _rag_graph_validate_patch,
    "rag.graph.apply_patch": _rag_graph_apply_patch,
    "rag.graph.attach_knowledge_store_to_node": _rag_graph_attach_knowledge_store,
    "rag.graph.set_pipeline_node_config": _rag_graph_set_node_config,
    "rag.compile_visual_pipeline": _rag_compile_visual_pipeline,
    "rag.get_executable_pipeline": _rag_get_executable_pipeline,
    "rag.get_executable_input_schema": _rag_get_executable_input_schema,
    "rag.create_job": _rag_create_job,
    "rag.get_job": _rag_get_job,
    "agents.list": _agents_list,
    "agents.get": _agents_get,
    "agents.create_shell": _agents_create_shell,
    "agents.create": _agents_create_or_update,
    "agents.update": _agents_create_or_update,
    "agents.graph.get": _agents_graph_get,
    "agents.graph.validate_patch": _agents_graph_validate_patch,
    "agents.graph.apply_patch": _agents_graph_apply_patch,
    "agents.graph.add_tool_to_agent_node": _agents_graph_add_tool,
    "agents.graph.remove_tool_from_agent_node": _agents_graph_remove_tool,
    "agents.graph.set_agent_model": _agents_graph_set_model,
    "agents.graph.set_agent_instructions": _agents_graph_set_instructions,
    "agents.publish": _agents_publish,
    "agents.validate": _agents_validate,
    "agents.nodes.catalog": _agents_nodes_catalog,
    "agents.nodes.schema": _agents_nodes_schema,
    "agents.nodes.validate": _agents_nodes_validate,
    "agents.execute": _agents_execute,
    "agents.start_run": _agents_start_run,
    "agents.get_run": _agents_get_run,
    "tools.list": _tools_list,
    "tools.get": _tools_get,
    "tools.create_or_update": _tools_create_or_update,
    "tools.publish": _tools_publish,
    "artifacts.list": _artifacts_list,
    "artifacts.get": _artifacts_get,
    "artifacts.create": _artifacts_create,
    "artifacts.update": _artifacts_update,
    "artifacts.convert_kind": _artifacts_convert_kind,
    "artifacts.create_test_run": _artifacts_create_test_run,
    "artifacts.publish": _artifacts_publish,
    "artifacts.delete": _artifacts_delete,
    "models.list": _models_list,
    "models.create_or_update": _models_create_or_update,
    "credentials.list": _credentials_list,
    "credentials.create_or_update": _credentials_create_or_update,
    "knowledge_stores.list": _knowledge_stores_list,
    "knowledge_stores.create_or_update": _knowledge_stores_create_or_update,
    "orchestration.join": _orchestration_join,
    "orchestration.cancel_subtree": _orchestration_cancel_subtree,
    "orchestration.evaluate_and_replan": _orchestration_evaluate_and_replan,
    "orchestration.query_tree": _orchestration_query_tree,
}


async def _dispatch_platform_native_with_context(*, tool_slug: str, payload: Any) -> dict[str, Any]:
    tool_payload = _normalize_payload(payload)
    tool_payload["tool_slug"] = tool_slug
    async with get_session() as db:
        runtime = NativePlatformToolRuntime(db=db, payload=tool_payload)
        result = await runtime.dispatch()
        if hasattr(db, "commit"):
            await db.commit()
        return result


@register_tool_function(PLATFORM_NATIVE_FUNCTIONS["platform-rag"])
async def platform_native_platform_rag(payload: Any) -> dict[str, Any]:
    return await _dispatch_platform_native_with_context(tool_slug="platform-rag", payload=payload)


@register_tool_function(PLATFORM_NATIVE_FUNCTIONS["platform-agents"])
async def platform_native_platform_agents(payload: Any) -> dict[str, Any]:
    return await _dispatch_platform_native_with_context(tool_slug="platform-agents", payload=payload)


@register_tool_function(PLATFORM_NATIVE_FUNCTIONS["platform-assets"])
async def platform_native_platform_assets(payload: Any) -> dict[str, Any]:
    return await _dispatch_platform_native_with_context(tool_slug="platform-assets", payload=payload)


@register_tool_function(PLATFORM_NATIVE_FUNCTIONS["platform-governance"])
async def platform_native_platform_governance(payload: Any) -> dict[str, Any]:
    return await _dispatch_platform_native_with_context(tool_slug="platform-governance", payload=payload)
