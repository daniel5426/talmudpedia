from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.db.postgres.models.registry import ToolDefinitionScope
from app.services.control_plane.artifact_admin_service import ArtifactAdminService, ArtifactRuntimeInput, CreateArtifactInput, UpdateArtifactInput
from app.services.control_plane.contracts import ListQuery
from app.services.control_plane.credentials_admin_service import CredentialsAdminService, serialize_credential
from app.services.control_plane.errors import not_found, validation
from app.services.control_plane.knowledge_store_admin_service import KnowledgeStoreAdminService
from app.services.control_plane.models_service import CreateModelInput, ListModelsInput, ModelRegistryService, UpdateModelInput, serialize_model
from app.services.control_plane.tool_registry_admin_service import ToolRegistryAdminService, serialize_tool
from app.services.control_plane.knowledge_store_admin_service import serialize_store
from app.services.platform_native.runtime import NativePlatformToolRuntime, parse_uuid
from app.services.prompt_library_service import PromptLibraryService


@dataclass(frozen=True)
class ToolRequest:
    name: str | None = None
    description: str | None = None
    scope: Any | None = ToolDefinitionScope.TENANT
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    config_schema: dict[str, Any] | None = None
    implementation_config: dict[str, Any] | None = None
    execution_config: dict[str, Any] | None = None
    implementation_type: Any | None = None
    status: Any | None = None
    is_active: bool | None = None
    artifact_id: Any | None = None
    artifact_version: str | None = None


async def tools_list(rt: NativePlatformToolRuntime) -> Any:
    ctx = await rt.build_control_plane_context()
    query = ListQuery.from_payload(rt.payload)
    tools, total = await ToolRegistryAdminService(rt.db).list_tools(
        ctx=ctx,
        scope=rt.payload.get("scope"),
        name=rt.payload.get("name"),
        is_active=rt.payload.get("is_active", True),
        status=rt.payload.get("status"),
        implementation_type=rt.payload.get("implementation_type"),
        tool_type=rt.payload.get("tool_type"),
        skip=query.skip,
        limit=query.limit,
    )
    return {
        "items": [serialize_tool(tool, view=query.view) for tool in tools],
        "total": total,
        "has_more": query.skip + len(tools) < total,
        "skip": query.skip,
        "limit": query.limit,
        "view": query.view,
    }


async def tools_get(rt: NativePlatformToolRuntime) -> Any:
    tool = await ToolRegistryAdminService(rt.db).get_tool(
        ctx=await rt.build_control_plane_context(),
        tool_id=parse_uuid(rt.payload.get("tool_id") or rt.payload.get("id")),
    )
    return serialize_tool(tool)


def _tool_request_from_payload(payload: dict[str, Any]) -> ToolRequest:
    return ToolRequest(
        **{
            key: (_normalize_tool_scope(value) if key == "scope" else value)
            for key, value in payload.items()
            if key in ToolRequest.__dataclass_fields__
        }
    )


async def tools_create(rt: NativePlatformToolRuntime) -> Any:
    ctx = await rt.build_control_plane_context()
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "name": rt.payload.get("name")}
    tool = await ToolRegistryAdminService(rt.db).create_tool(ctx=ctx, request=_tool_request_from_payload(rt.payload))
    return serialize_tool(tool)


async def tools_update(rt: NativePlatformToolRuntime) -> Any:
    ctx = await rt.build_control_plane_context()
    tool_id = parse_uuid(rt.payload.get("tool_id") or rt.payload.get("id"))
    if tool_id is None:
        raise not_found("Tool not found")
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "tool_id": str(tool_id)}
    update_fields = {
        key
        for key in rt.payload.keys()
        if key in ToolRequest.__dataclass_fields__ and key not in {"tool_id", "id"}
    }
    if not update_fields:
        raise validation("At least one update field is required.")
    request = _tool_request_from_payload(rt.payload)
    tool = await ToolRegistryAdminService(rt.db).update_tool(ctx=ctx, tool_id=tool_id, request=request)
    return serialize_tool(tool)


async def tools_create_or_update(rt: NativePlatformToolRuntime) -> Any:
    ctx = await rt.build_control_plane_context()
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "name": rt.payload.get("name")}
    tool_id = parse_uuid(rt.payload.get("tool_id") or rt.payload.get("id"))
    if tool_id is not None:
        patch = dict(rt.payload.get("patch") or rt.payload)
        tool = await ToolRegistryAdminService(rt.db).update_tool(ctx=ctx, tool_id=tool_id, request=_tool_request_from_payload(patch))
        return serialize_tool(tool)
    tool = await ToolRegistryAdminService(rt.db).create_tool(ctx=ctx, request=_tool_request_from_payload(rt.payload))
    return serialize_tool(tool)


async def tools_publish(rt: NativePlatformToolRuntime) -> Any:
    tool_id = parse_uuid(rt.payload.get("tool_id") or rt.payload.get("id"))
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "tool_id": str(tool_id)}
    tool = await ToolRegistryAdminService(rt.db).publish_tool(
        ctx=await rt.build_control_plane_context(),
        tool_id=tool_id,
    )
    return serialize_tool(tool)


async def models_list(rt: NativePlatformToolRuntime) -> Any:
    ctx = await rt.build_control_plane_context()
    query = ListQuery.from_payload(rt.payload)
    models, total = await ModelRegistryService(rt.db).list_models(
        ctx=ctx,
        params=ListModelsInput(
            capability_type=rt.payload.get("capability_type"),
            status=rt.payload.get("status"),
            is_active=rt.payload.get("is_active", True),
            skip=query.skip,
            limit=query.limit,
        ),
    )
    return {
        "items": [serialize_model(model, view=query.view) for model in models],
        "total": total,
        "has_more": query.skip + len(models) < total,
        "skip": query.skip,
        "limit": query.limit,
        "view": query.view,
    }


async def models_create_or_update(rt: NativePlatformToolRuntime) -> Any:
    ctx = await rt.build_control_plane_context()
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "name": rt.payload.get("name")}
    model_id = parse_uuid(rt.payload.get("model_id") or rt.payload.get("id"))
    if model_id is not None:
        patch = dict(rt.payload.get("patch") or rt.payload)
        model = await ModelRegistryService(rt.db).update_model(
            ctx=ctx,
            model_id=model_id,
            params=UpdateModelInput(**{key: value for key, value in patch.items() if key in UpdateModelInput.__dataclass_fields__}),
        )
    else:
        model = await ModelRegistryService(rt.db).create_model(
            ctx=ctx,
            params=CreateModelInput(**{key: value for key, value in rt.payload.items() if key in CreateModelInput.__dataclass_fields__}),
        )
    return {
        "id": str(model.id),
        "name": model.name,
        "status": getattr(model.status, "value", model.status),
        "is_active": bool(model.is_active),
    }


def _serialize_prompt(prompt: Any, *, view: str) -> dict[str, Any]:
    payload = {
        "id": str(prompt.id),
        "name": str(prompt.name or ""),
        "description": prompt.description,
        "scope": str(getattr(prompt.scope, "value", prompt.scope)),
        "status": str(getattr(prompt.status, "value", prompt.status)),
        "managed_by": prompt.managed_by,
        "allowed_surfaces": list(prompt.allowed_surfaces or []),
        "tags": list(prompt.tags or []),
        "version": int(prompt.version or 1),
        "updated_at": prompt.updated_at.isoformat() if getattr(prompt, "updated_at", None) else None,
    }
    if str(view or "summary").strip().lower() == "full":
        payload["content"] = str(prompt.content or "")
    return payload


async def prompts_list(rt: NativePlatformToolRuntime) -> Any:
    ctx = await rt.build_control_plane_context()
    query = ListQuery.from_payload(rt.payload)
    prompts, total = await PromptLibraryService(
        rt.db,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user_id,
        is_service=ctx.is_service,
    ).list_prompts(
        q=rt.payload.get("q"),
        status=rt.payload.get("status"),
        limit=query.limit,
        offset=query.skip,
    )
    return {
        "items": [_serialize_prompt(item, view=query.view) for item in prompts],
        "total": total,
        "has_more": query.skip + len(prompts) < total,
        "skip": query.skip,
        "limit": query.limit,
        "view": query.view,
    }


async def credentials_list(rt: NativePlatformToolRuntime) -> Any:
    ctx = await rt.build_control_plane_context()
    query = ListQuery.from_payload(rt.payload)
    credentials = await CredentialsAdminService(rt.db).list_credentials(ctx=ctx, category=rt.payload.get("category"))
    sliced = credentials[query.skip: query.skip + query.limit]
    return {
        "items": [serialize_credential(item, view=query.view) for item in sliced],
        "total": len(credentials),
        "has_more": query.skip + len(sliced) < len(credentials),
        "skip": query.skip,
        "limit": query.limit,
        "view": query.view,
    }


async def credentials_create_or_update(rt: NativePlatformToolRuntime) -> Any:
    ctx = await rt.build_control_plane_context()
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "display_name": rt.payload.get("display_name")}
    credential_id = parse_uuid(rt.payload.get("credential_id") or rt.payload.get("id"))
    if credential_id is not None:
        patch = dict(rt.payload.get("patch") or rt.payload)
        credential = await CredentialsAdminService(rt.db).update_credential(ctx=ctx, credential_id=credential_id, patch=patch)
    else:
        credential = await CredentialsAdminService(rt.db).create_credential(
            ctx=ctx,
            category=rt.payload.get("category"),
            provider_key=rt.payload.get("provider_key"),
            provider_variant=rt.payload.get("provider_variant"),
            display_name=rt.payload.get("display_name"),
            credentials=rt.payload.get("credentials") if isinstance(rt.payload.get("credentials"), dict) else {},
            is_enabled=bool(rt.payload.get("is_enabled", True)),
            is_default=bool(rt.payload.get("is_default", False)),
        )
    return {"id": str(credential.id), "display_name": credential.display_name}


async def knowledge_stores_list(rt: NativePlatformToolRuntime) -> Any:
    ctx = await rt.build_control_plane_context()
    query = ListQuery.from_payload(rt.payload)
    stores = await KnowledgeStoreAdminService(rt.db).list_stores(ctx=ctx)
    sliced = stores[query.skip: query.skip + query.limit]
    return {
        "items": [serialize_store(store, view=query.view) for store in sliced],
        "total": len(stores),
        "has_more": query.skip + len(sliced) < len(stores),
        "skip": query.skip,
        "limit": query.limit,
        "view": query.view,
    }


async def knowledge_stores_create(rt: NativePlatformToolRuntime) -> Any:
    ctx = await rt.build_control_plane_context()
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "name": rt.payload.get("name")}
    store = await KnowledgeStoreAdminService(rt.db).create_store(
        ctx=ctx,
        organization_id=None,
        name=rt.payload.get("name"),
        description=rt.payload.get("description"),
        embedding_model_id=rt.payload.get("embedding_model_id"),
        chunking_strategy=rt.payload.get("chunking_strategy") if isinstance(rt.payload.get("chunking_strategy"), dict) else None,
        retrieval_policy=rt.payload.get("retrieval_policy"),
        backend=rt.payload.get("backend"),
        backend_config=rt.payload.get("backend_config") if isinstance(rt.payload.get("backend_config"), dict) else None,
        credentials_ref=rt.payload.get("credentials_ref"),
    )
    return {"id": str(store.id), "name": store.name}


async def knowledge_stores_update(rt: NativePlatformToolRuntime) -> Any:
    ctx = await rt.build_control_plane_context()
    store_id = parse_uuid(rt.payload.get("store_id") or rt.payload.get("knowledge_store_id") or rt.payload.get("id"))
    if store_id is None:
        raise not_found("Knowledge store not found")
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "store_id": str(store_id)}
    patch = {
        key: value
        for key, value in rt.payload.items()
        if key in {"name", "description", "retrieval_policy", "credentials_ref"}
    }
    if not patch:
        raise validation("At least one update field is required.")
    store = await KnowledgeStoreAdminService(rt.db).update_store(
        ctx=ctx,
        store_id=store_id,
        organization_id=None,
        patch=patch,
    )
    return {"id": str(store.id), "name": store.name}


async def knowledge_stores_create_or_update(rt: NativePlatformToolRuntime) -> Any:
    ctx = await rt.build_control_plane_context()
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "name": rt.payload.get("name")}
    store_id = parse_uuid(rt.payload.get("store_id") or rt.payload.get("knowledge_store_id") or rt.payload.get("id"))
    if store_id is not None:
        patch = dict(rt.payload.get("patch") or rt.payload)
        store = await KnowledgeStoreAdminService(rt.db).update_store(
            ctx=ctx,
            store_id=store_id,
            organization_id=rt.payload.get("organization_id"),
            patch=patch,
        )
        return {"id": str(store.id), "name": store.name}
    store = await KnowledgeStoreAdminService(rt.db).create_store(
        ctx=ctx,
        organization_id=rt.payload.get("organization_id"),
        name=rt.payload.get("name"),
        description=rt.payload.get("description"),
        embedding_model_id=rt.payload.get("embedding_model_id"),
        chunking_strategy=rt.payload.get("chunking_strategy") if isinstance(rt.payload.get("chunking_strategy"), dict) else None,
        retrieval_policy=rt.payload.get("retrieval_policy"),
        backend=rt.payload.get("backend"),
        backend_config=rt.payload.get("backend_config") if isinstance(rt.payload.get("backend_config"), dict) else None,
        credentials_ref=rt.payload.get("credentials_ref"),
    )
    return {"id": str(store.id), "name": store.name}


async def artifacts_list(rt: NativePlatformToolRuntime) -> Any:
    page = await ArtifactAdminService(rt.db).list_artifacts(
        ctx=await rt.build_control_plane_context(),
        query=ListQuery.from_payload(rt.payload),
    )
    return page.to_payload()


async def artifacts_get(rt: NativePlatformToolRuntime) -> Any:
    artifact_id = parse_uuid(rt.payload.get("artifact_id") or rt.payload.get("id"))
    return await ArtifactAdminService(rt.db).get_artifact(ctx=await rt.build_control_plane_context(), artifact_id=artifact_id)


async def artifacts_create(rt: NativePlatformToolRuntime) -> Any:
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "display_name": str(rt.payload.get("display_name") or "")}
    runtime = rt.payload.get("runtime") if isinstance(rt.payload.get("runtime"), dict) else {}
    return await ArtifactAdminService(rt.db).create_artifact(
        ctx=await rt.build_control_plane_context(),
        params=CreateArtifactInput(
            display_name=str(rt.payload.get("display_name") or ""),
            description=rt.payload.get("description"),
            kind=str(rt.payload.get("kind") or "tool_impl"),
            runtime=ArtifactRuntimeInput(
                language=str(runtime.get("language") or "python"),
                source_files=list(runtime.get("source_files") or []),
                entry_module_path=str(runtime.get("entry_module_path") or "main.py"),
                dependencies=list(runtime.get("dependencies") or runtime.get("python_dependencies") or []),
                runtime_target=str(runtime.get("runtime_target") or "cloudflare_workers"),
            ),
            capabilities=rt.payload.get("capabilities") if isinstance(rt.payload.get("capabilities"), dict) else {},
            config_schema=rt.payload.get("config_schema") if isinstance(rt.payload.get("config_schema"), dict) else {},
            agent_contract=rt.payload.get("agent_contract") if isinstance(rt.payload.get("agent_contract"), dict) else None,
            rag_contract=rt.payload.get("rag_contract") if isinstance(rt.payload.get("rag_contract"), dict) else None,
            tool_contract=rt.payload.get("tool_contract") if isinstance(rt.payload.get("tool_contract"), dict) else None,
        ),
    )


async def artifacts_update(rt: NativePlatformToolRuntime) -> Any:
    artifact_id = parse_uuid(rt.payload.get("artifact_id") or rt.payload.get("id"))
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "artifact_id": str(artifact_id)}
    patch = dict(rt.payload.get("patch") or {})
    runtime = patch.get("runtime") if isinstance(patch.get("runtime"), dict) else None
    return await ArtifactAdminService(rt.db).update_artifact(
        ctx=await rt.build_control_plane_context(),
        artifact_id=artifact_id,
        params=UpdateArtifactInput(
            display_name=patch.get("display_name"),
            description=patch.get("description"),
            runtime=ArtifactRuntimeInput(
                language=str(runtime.get("language") or "python"),
                source_files=list(runtime.get("source_files") or []),
                entry_module_path=str(runtime.get("entry_module_path") or "main.py"),
                dependencies=list(runtime.get("dependencies") or runtime.get("python_dependencies") or []),
                runtime_target=str(runtime.get("runtime_target") or "cloudflare_workers"),
            ) if runtime is not None else None,
            capabilities=patch.get("capabilities") if isinstance(patch.get("capabilities"), dict) else None,
            config_schema=patch.get("config_schema") if isinstance(patch.get("config_schema"), dict) else None,
            agent_contract=patch.get("agent_contract") if isinstance(patch.get("agent_contract"), dict) else None,
            rag_contract=patch.get("rag_contract") if isinstance(patch.get("rag_contract"), dict) else None,
            tool_contract=patch.get("tool_contract") if isinstance(patch.get("tool_contract"), dict) else None,
        ),
    )


async def artifacts_convert_kind(rt: NativePlatformToolRuntime) -> Any:
    artifact_id = parse_uuid(rt.payload.get("artifact_id") or rt.payload.get("id"))
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "artifact_id": str(artifact_id)}
    return await ArtifactAdminService(rt.db).convert_kind(
        ctx=await rt.build_control_plane_context(),
        artifact_id=artifact_id,
        kind=str(rt.payload.get("kind") or ""),
        agent_contract=rt.payload.get("agent_contract") if isinstance(rt.payload.get("agent_contract"), dict) else None,
        rag_contract=rt.payload.get("rag_contract") if isinstance(rt.payload.get("rag_contract"), dict) else None,
        tool_contract=rt.payload.get("tool_contract") if isinstance(rt.payload.get("tool_contract"), dict) else None,
    )


async def artifacts_create_test_run(rt: NativePlatformToolRuntime) -> Any:
    return await ArtifactAdminService(rt.db).create_test_run(
        ctx=await rt.build_control_plane_context(),
        artifact_id=parse_uuid(rt.payload.get("artifact_id") or rt.payload.get("id")),
        source_files=list(rt.payload.get("source_files") or []),
        entry_module_path=rt.payload.get("entry_module_path"),
        input_data=rt.payload.get("input") if "input" in rt.payload else rt.payload.get("input_data"),
        config=rt.payload.get("config") if isinstance(rt.payload.get("config"), dict) else {},
        dependencies=list(rt.payload.get("dependencies") or []),
        language=rt.payload.get("language"),
        kind=rt.payload.get("kind"),
        runtime_target=rt.payload.get("runtime_target"),
        capabilities=rt.payload.get("capabilities") if isinstance(rt.payload.get("capabilities"), dict) else {},
        config_schema=rt.payload.get("config_schema") if isinstance(rt.payload.get("config_schema"), dict) else {},
        agent_contract=rt.payload.get("agent_contract") if isinstance(rt.payload.get("agent_contract"), dict) else None,
        rag_contract=rt.payload.get("rag_contract") if isinstance(rt.payload.get("rag_contract"), dict) else None,
        tool_contract=rt.payload.get("tool_contract") if isinstance(rt.payload.get("tool_contract"), dict) else None,
    )


async def artifacts_publish(rt: NativePlatformToolRuntime) -> Any:
    artifact_id = parse_uuid(rt.payload.get("artifact_id") or rt.payload.get("id"))
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "artifact_id": str(artifact_id)}
    return await ArtifactAdminService(rt.db).publish_artifact(ctx=await rt.build_control_plane_context(), artifact_id=artifact_id)


async def artifacts_delete(rt: NativePlatformToolRuntime) -> Any:
    artifact_id = parse_uuid(rt.payload.get("artifact_id") or rt.payload.get("id"))
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "artifact_id": str(artifact_id)}
    return await ArtifactAdminService(rt.db).delete_artifact(ctx=await rt.build_control_plane_context(), artifact_id=artifact_id)


def _normalize_tool_scope(value: Any) -> Any:
    if value is None:
        return ToolDefinitionScope.TENANT
    if isinstance(value, ToolDefinitionScope):
        return value
    raw = str(getattr(value, "value", value)).strip().lower()
    for candidate in ToolDefinitionScope:
        if candidate.value == raw:
            return candidate
    return value
