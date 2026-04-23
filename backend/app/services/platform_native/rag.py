from __future__ import annotations

import asyncio
from typing import Any

from app.services.control_plane.contracts import ListQuery
from app.services.control_plane.errors import not_found, validation
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


_RAG_UPDATE_FIELDS = ("name", "description", "nodes", "edges")


def _graph_nodes_and_edges(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes = payload.get("nodes")
    edges = payload.get("edges")
    if not isinstance(nodes, list):
        raise validation("nodes must be an array", field="nodes")
    if not isinstance(edges, list):
        raise validation("edges must be an array", field="edges")
    return list(nodes), list(edges)


async def rag_list_visual_pipelines(rt: NativePlatformToolRuntime) -> Any:
    page = await RagAdminService(rt.db).list_visual_pipelines(
        ctx=await rt.build_control_plane_context(),
        query=ListQuery.from_payload(rt.payload),
    )
    return page.to_payload()


async def rag_operators_catalog(rt: NativePlatformToolRuntime) -> Any:
    return await RagAdminService(rt.db).operators_catalog(
        ctx=await rt.build_control_plane_context(),
        pipeline_type=str(rt.payload.get("pipeline_type") or ""),
    )


async def rag_operators_schema(rt: NativePlatformToolRuntime) -> Any:
    return await RagAdminService(rt.db).operators_schema(
        ctx=await rt.build_control_plane_context(),
        pipeline_type=str(rt.payload.get("pipeline_type") or ""),
        operator_ids=list(rt.payload.get("operator_ids") or []),
    )


async def rag_create_pipeline_shell(rt: NativePlatformToolRuntime) -> Any:
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "name": str(rt.payload.get("name") or "")}
    nodes, edges = _graph_nodes_and_edges(_pipeline_shell_graph())
    return await RagAdminService(rt.db).create_pipeline(
        ctx=await rt.build_control_plane_context(),
        params=CreatePipelineInput(
            name=str(rt.payload.get("name") or ""),
            description=rt.payload.get("description"),
            pipeline_type=str(rt.payload.get("pipeline_type") or ""),
            nodes=nodes,
            edges=edges,
        ),
    )


async def rag_create_visual_pipeline(rt: NativePlatformToolRuntime) -> Any:
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "name": str(rt.payload.get("name") or "")}
    if "graph_definition" in rt.payload:
        raise validation(
            "graph_definition is not supported; send nodes and edges at top level",
            field="graph_definition",
            errors=[
                {
                    "code": "LEGACY_FIELD_NOT_ALLOWED",
                    "path": "/graph_definition",
                    "message": "Use top-level nodes and edges instead of graph_definition.",
                }
            ],
        )
    if not str(rt.payload.get("pipeline_type") or "").strip():
        raise validation("pipeline_type is required", field="pipeline_type")
    nodes, edges = _graph_nodes_and_edges(rt.payload)
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


async def rag_update_visual_pipeline(rt: NativePlatformToolRuntime) -> Any:
    pipeline_id = parse_uuid(rt.payload.get("pipeline_id") or rt.payload.get("id"))
    if pipeline_id is None:
        raise not_found("Pipeline not found")
    if rt.dry_run:
        return {"status": "skipped", "dry_run": True, "pipeline_id": str(pipeline_id)}
    if "patch" in rt.payload:
        raise validation(
            "patch is not supported; send direct top-level update fields",
            field="patch",
            errors=[
                {
                    "code": "LEGACY_FIELD_NOT_ALLOWED",
                    "path": "/patch",
                    "message": "Use direct top-level update fields instead of patch.",
                }
            ],
        )
    if not any(field in rt.payload for field in _RAG_UPDATE_FIELDS):
        raise validation(
            "At least one update field is required.",
            errors=[
                {
                    "code": "MISSING_UPDATE_FIELDS",
                    "path": "/",
                    "message": "Provide at least one of name, description, or nodes+edges.",
                }
            ],
        )
    has_nodes = "nodes" in rt.payload
    has_edges = "edges" in rt.payload
    if has_nodes != has_edges:
        raise validation(
            "nodes and edges must be provided together",
            errors=[
                {
                    "code": "PARTIAL_GRAPH_UPDATE_NOT_ALLOWED",
                    "path": "/nodes" if has_nodes else "/edges",
                    "message": "Provide both nodes and edges together for graph updates.",
                }
            ],
        )
    nodes = None
    edges = None
    if has_nodes and has_edges:
        nodes, edges = _graph_nodes_and_edges(rt.payload)
    return await RagAdminService(rt.db).update_pipeline(
        ctx=await rt.build_control_plane_context(),
        pipeline_id=pipeline_id,
        params=UpdatePipelineInput(
            name=rt.payload.get("name"),
            description=rt.payload.get("description"),
            nodes=nodes or None,
            edges=edges or None,
        ),
    )


async def rag_graph_get(rt: NativePlatformToolRuntime) -> Any:
    pipeline_id = parse_uuid(rt.payload.get("pipeline_id") or rt.payload.get("id"))
    if pipeline_id is None:
        raise not_found("Pipeline not found")
    ctx = await rt.build_control_plane_context()
    return await RagGraphMutationService(rt.db, organization_id=ctx.organization_id, project_id=ctx.project_id).get_graph(pipeline_id)


async def rag_graph_validate_patch(rt: NativePlatformToolRuntime) -> Any:
    pipeline_id = parse_uuid(rt.payload.get("pipeline_id") or rt.payload.get("id"))
    if pipeline_id is None:
        raise not_found("Pipeline not found")
    ctx = await rt.build_control_plane_context()
    return await RagGraphMutationService(rt.db, organization_id=ctx.organization_id, project_id=ctx.project_id).validate_patch(
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
    return await RagGraphMutationService(rt.db, organization_id=ctx.organization_id, project_id=ctx.project_id).apply_patch(
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
    return await RagGraphMutationService(rt.db, organization_id=ctx.organization_id, project_id=ctx.project_id).attach_knowledge_store_to_node(
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
    return await RagGraphMutationService(rt.db, organization_id=ctx.organization_id, project_id=ctx.project_id).set_pipeline_node_config(
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
