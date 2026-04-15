from __future__ import annotations

import asyncio
from typing import Any

from app.services.control_plane.contracts import ListQuery
from app.services.control_plane.errors import not_found
from app.services.control_plane.rag_admin_service import (
    CreatePipelineInput,
    RagAdminService,
    UpdatePipelineInput,
    dispatch_pipeline_job_background,
)
from app.services.rag_graph_mutation_service import RagGraphMutationService
from app.services.platform_native.runtime import NativePlatformToolRuntime, parse_uuid


def _pipeline_shell_graph() -> dict[str, Any]:
    return {
        "nodes": [
            {"id": "query_input_1", "category": "input", "operator": "query_input", "position": {"x": 0, "y": 0}, "config": {}},
            {"id": "model_embedder_1", "category": "embedding", "operator": "model_embedder", "position": {"x": 220, "y": 0}, "config": {}},
            {"id": "vector_search_1", "category": "retrieval", "operator": "vector_search", "position": {"x": 440, "y": 0}, "config": {}},
            {"id": "retrieval_result_1", "category": "output", "operator": "retrieval_result", "position": {"x": 660, "y": 0}, "config": {}},
        ],
        "edges": [
            {"id": "edge_query_to_embed", "source": "query_input_1", "target": "model_embedder_1"},
            {"id": "edge_embed_to_search", "source": "model_embedder_1", "target": "vector_search_1"},
            {"id": "edge_search_to_result", "source": "vector_search_1", "target": "retrieval_result_1"},
        ],
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


async def rag_list_visual_pipelines(rt: NativePlatformToolRuntime) -> Any:
    page = await RagAdminService(rt.db).list_visual_pipelines(
        ctx=await rt.build_control_plane_context(),
        query=ListQuery.from_payload(rt.payload),
    )
    return page.to_payload()


async def rag_operators_catalog(rt: NativePlatformToolRuntime) -> Any:
    return await RagAdminService(rt.db).operators_catalog(ctx=await rt.build_control_plane_context())


async def rag_operators_schema(rt: NativePlatformToolRuntime) -> Any:
    return await RagAdminService(rt.db).operators_schema(
        ctx=await rt.build_control_plane_context(),
        operator_ids=list(rt.payload.get("operator_ids") or []),
    )


async def rag_create_pipeline_shell(rt: NativePlatformToolRuntime) -> Any:
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "name": str(rt.payload.get("name") or "")}
    nodes, edges = _normalize_graph_definition(_pipeline_shell_graph())
    return await RagAdminService(rt.db).create_pipeline(
        ctx=await rt.build_control_plane_context(),
        params=CreatePipelineInput(
            name=str(rt.payload.get("name") or ""),
            description=rt.payload.get("description"),
            pipeline_type=str(rt.payload.get("pipeline_type") or "retrieval"),
            nodes=nodes,
            edges=edges,
        ),
    )


async def rag_create_visual_pipeline(rt: NativePlatformToolRuntime) -> Any:
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "name": str(rt.payload.get("name") or "")}
    nodes, edges = _normalize_graph_definition(rt.payload)
    return await RagAdminService(rt.db).create_pipeline(
        ctx=await rt.build_control_plane_context(),
        params=CreatePipelineInput(
            name=str(rt.payload.get("name") or ""),
            description=rt.payload.get("description"),
            pipeline_type=str(rt.payload.get("pipeline_type") or "retrieval"),
            nodes=nodes,
            edges=edges,
            org_unit_id=parse_uuid(rt.payload.get("org_unit_id")),
        ),
    )


async def rag_update_visual_pipeline(rt: NativePlatformToolRuntime) -> Any:
    pipeline_id = parse_uuid(rt.payload.get("pipeline_id") or rt.payload.get("id"))
    if pipeline_id is None:
        raise not_found("Pipeline not found")
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "pipeline_id": str(pipeline_id)}
    patch = dict(rt.payload.get("patch") or {})
    nodes, edges = _normalize_graph_definition(patch)
    return await RagAdminService(rt.db).update_pipeline(
        ctx=await rt.build_control_plane_context(),
        pipeline_id=pipeline_id,
        params=UpdatePipelineInput(
            name=patch.get("name"),
            description=patch.get("description"),
            pipeline_type=patch.get("pipeline_type"),
            nodes=nodes or None,
            edges=edges or None,
        ),
    )


async def rag_graph_get(rt: NativePlatformToolRuntime) -> Any:
    pipeline_id = parse_uuid(rt.payload.get("pipeline_id") or rt.payload.get("id"))
    if pipeline_id is None:
        raise not_found("Pipeline not found")
    ctx = await rt.build_control_plane_context()
    return await RagGraphMutationService(rt.db, tenant_id=ctx.tenant_id).get_graph(pipeline_id)


async def rag_graph_validate_patch(rt: NativePlatformToolRuntime) -> Any:
    pipeline_id = parse_uuid(rt.payload.get("pipeline_id") or rt.payload.get("id"))
    if pipeline_id is None:
        raise not_found("Pipeline not found")
    ctx = await rt.build_control_plane_context()
    return await RagGraphMutationService(rt.db, tenant_id=ctx.tenant_id).validate_patch(
        pipeline_id,
        list(rt.payload.get("operations") or []),
    )


async def rag_graph_apply_patch(rt: NativePlatformToolRuntime) -> Any:
    pipeline_id = parse_uuid(rt.payload.get("pipeline_id") or rt.payload.get("id"))
    if pipeline_id is None:
        raise not_found("Pipeline not found")
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "pipeline_id": str(pipeline_id)}
    ctx = await rt.build_control_plane_context()
    return await RagGraphMutationService(rt.db, tenant_id=ctx.tenant_id).apply_patch(
        pipeline_id,
        list(rt.payload.get("operations") or []),
    )


async def rag_graph_attach_knowledge_store(rt: NativePlatformToolRuntime) -> Any:
    pipeline_id = parse_uuid(rt.payload.get("pipeline_id") or rt.payload.get("id"))
    if pipeline_id is None:
        raise not_found("Pipeline not found")
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "pipeline_id": str(pipeline_id)}
    ctx = await rt.build_control_plane_context()
    return await RagGraphMutationService(rt.db, tenant_id=ctx.tenant_id).attach_knowledge_store_to_node(
        pipeline_id,
        node_id=str(rt.payload.get("node_id") or ""),
        knowledge_store_id=str(rt.payload.get("knowledge_store_id") or ""),
    )


async def rag_graph_set_pipeline_node_config(rt: NativePlatformToolRuntime) -> Any:
    pipeline_id = parse_uuid(rt.payload.get("pipeline_id") or rt.payload.get("id"))
    if pipeline_id is None:
        raise not_found("Pipeline not found")
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "pipeline_id": str(pipeline_id)}
    ctx = await rt.build_control_plane_context()
    return await RagGraphMutationService(rt.db, tenant_id=ctx.tenant_id).set_pipeline_node_config(
        pipeline_id,
        node_id=str(rt.payload.get("node_id") or ""),
        path=str(rt.payload.get("path") or ""),
        value=rt.payload.get("value"),
    )


async def rag_compile_visual_pipeline(rt: NativePlatformToolRuntime) -> Any:
    pipeline_id = parse_uuid(rt.payload.get("pipeline_id") or rt.payload.get("id"))
    if pipeline_id is None:
        raise not_found("Pipeline not found")
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "pipeline_id": str(pipeline_id)}
    return await RagAdminService(rt.db).compile_pipeline(ctx=await rt.build_control_plane_context(), pipeline_id=pipeline_id)


async def rag_get_executable_pipeline(rt: NativePlatformToolRuntime) -> Any:
    executable_pipeline_id = parse_uuid(rt.payload.get("executable_pipeline_id") or rt.payload.get("pipeline_id") or rt.payload.get("id"))
    if executable_pipeline_id is None:
        raise not_found("Executable pipeline not found")
    return await RagAdminService(rt.db).get_executable_pipeline(
        ctx=await rt.build_control_plane_context(),
        executable_pipeline_id=executable_pipeline_id,
    )


async def rag_get_executable_input_schema(rt: NativePlatformToolRuntime) -> Any:
    executable_pipeline_id = parse_uuid(rt.payload.get("executable_pipeline_id") or rt.payload.get("pipeline_id") or rt.payload.get("id"))
    if executable_pipeline_id is None:
        raise not_found("Executable pipeline not found")
    return await RagAdminService(rt.db).get_executable_input_schema(
        ctx=await rt.build_control_plane_context(),
        executable_pipeline_id=executable_pipeline_id,
    )


async def rag_create_job(rt: NativePlatformToolRuntime) -> Any:
    executable_pipeline_id = parse_uuid(rt.payload.get("executable_pipeline_id") or rt.payload.get("pipeline_id") or rt.payload.get("id"))
    if executable_pipeline_id is None:
        raise not_found("Executable pipeline not found")
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True}
    operation = await RagAdminService(rt.db).create_job(
        ctx=await rt.build_control_plane_context(),
        executable_pipeline_id=executable_pipeline_id,
        input_params=rt.payload.get("input_params") if isinstance(rt.payload.get("input_params"), dict) else {},
    )
    job_id = parse_uuid(((operation.get("operation") or {}).get("id")) if isinstance(operation, dict) else None)
    if job_id is not None:
        asyncio.create_task(
            dispatch_pipeline_job_background(job_id, artifact_queue_class="artifact_prod_background")
        )
    return operation


async def rag_get_job(rt: NativePlatformToolRuntime) -> Any:
    job_id = parse_uuid(rt.payload.get("job_id") or rt.payload.get("id"))
    if job_id is None:
        raise not_found("Job not found")
    return await RagAdminService(rt.db).get_job(ctx=await rt.build_control_plane_context(), job_id=job_id)
