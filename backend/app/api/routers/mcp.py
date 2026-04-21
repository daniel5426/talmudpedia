from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_principal, require_scopes
from app.api.schemas.mcp import (
    McpAccountConnectionResponse,
    McpAgentMountCreateRequest,
    McpAgentMountResponse,
    McpAgentMountUpdateRequest,
    McpAuthStartResponse,
    McpDiscoveredToolResponse,
    McpServerCreateRequest,
    McpServerResponse,
    McpServerUpdateRequest,
)
from app.core.runtime_urls import resolve_local_backend_origin
from app.db.postgres.models.mcp import McpOauthState, McpServer
from app.db.postgres.session import get_db
from app.services.mcp_service import McpNotFoundError, McpService, McpServiceError


router = APIRouter(tags=["mcp"])


def _organization_id_from_principal(principal: dict) -> UUID:
    try:
        return UUID(str(principal.get("organization_id")))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid organization context") from exc


def _user_id_from_principal(principal: dict) -> UUID:
    user = principal.get("user")
    if user is not None and getattr(user, "id", None) is not None:
        return user.id
    try:
        return UUID(str(principal.get("user_id")))
    except Exception as exc:
        raise HTTPException(status_code=403, detail="Authenticated user required") from exc


def _serialize_server(server) -> McpServerResponse:
    return McpServerResponse(**McpService(None, server.organization_id)._server_secret_payload(server), id=server.id, organization_id=server.organization_id)


def _serialize_tool(tool) -> McpDiscoveredToolResponse:
    return McpDiscoveredToolResponse(
        id=tool.id,
        server_id=tool.server_id,
        snapshot_version=tool.snapshot_version,
        name=tool.name,
        title=tool.title,
        description=tool.description,
        input_schema=tool.input_schema or {},
        annotations=tool.annotations or {},
        tool_metadata=tool.tool_metadata or {},
        created_at=tool.created_at,
    )


def _serialize_connection(connection) -> McpAccountConnectionResponse:
    return McpAccountConnectionResponse(
        server_id=connection.server_id,
        user_id=connection.user_id,
        status=connection.status,
        scopes=list(connection.scopes or []),
        account_metadata=connection.account_metadata or {},
        last_error=connection.last_error,
        access_token_expires_at=connection.access_token_expires_at,
        refresh_token_expires_at=connection.refresh_token_expires_at,
        last_refreshed_at=connection.last_refreshed_at,
        last_used_at=connection.last_used_at,
        created_at=connection.created_at,
        updated_at=connection.updated_at,
    )


def _serialize_mount(mount) -> McpAgentMountResponse:
    return McpAgentMountResponse(
        id=mount.id,
        agent_id=mount.agent_id,
        server_id=mount.server_id,
        applied_snapshot_version=mount.applied_snapshot_version,
        approval_policy=mount.approval_policy,
        is_active=mount.is_active,
        created_at=mount.created_at,
        updated_at=mount.updated_at,
    )


@router.post("/mcp/servers", response_model=McpServerResponse)
async def create_mcp_server(
    request: McpServerCreateRequest,
    principal: dict = Depends(require_scopes("tools.write")),
    db: AsyncSession = Depends(get_db),
):
    service = McpService(db, _organization_id_from_principal(principal))
    try:
        server = await service.create_server(request.model_dump(), created_by=_user_id_from_principal(principal))
        await db.commit()
        await db.refresh(server)
        return _serialize_server(server)
    except McpServiceError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/mcp/servers", response_model=list[McpServerResponse])
async def list_mcp_servers(
    principal: dict = Depends(require_scopes("tools.read")),
    db: AsyncSession = Depends(get_db),
):
    service = McpService(db, _organization_id_from_principal(principal))
    servers = await service.list_servers()
    return [_serialize_server(server) for server in servers]


@router.get("/mcp/servers/{server_id}", response_model=McpServerResponse)
async def get_mcp_server(
    server_id: UUID,
    principal: dict = Depends(require_scopes("tools.read")),
    db: AsyncSession = Depends(get_db),
):
    service = McpService(db, _organization_id_from_principal(principal))
    try:
        server = await service._get_server(server_id)
        return _serialize_server(server)
    except McpNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/mcp/servers/{server_id}", response_model=McpServerResponse)
async def patch_mcp_server(
    server_id: UUID,
    request: McpServerUpdateRequest,
    principal: dict = Depends(require_scopes("tools.write")),
    db: AsyncSession = Depends(get_db),
):
    service = McpService(db, _organization_id_from_principal(principal))
    try:
        server = await service.update_server(server_id, request.model_dump(exclude_unset=True))
        await db.commit()
        await db.refresh(server)
        return _serialize_server(server)
    except McpNotFoundError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except McpServiceError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/mcp/servers/{server_id}/test")
async def test_mcp_server(
    server_id: UUID,
    principal: dict = Depends(require_scopes("tools.write")),
    db: AsyncSession = Depends(get_db),
):
    service = McpService(db, _organization_id_from_principal(principal))
    try:
        payload = await service.test_server(server_id)
        await db.commit()
        return payload
    except McpNotFoundError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except McpServiceError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/mcp/servers/{server_id}/sync")
async def sync_mcp_server(
    server_id: UUID,
    principal: dict = Depends(require_scopes("tools.write")),
    db: AsyncSession = Depends(get_db),
):
    service = McpService(db, _organization_id_from_principal(principal))
    try:
        payload = await service.sync_server(server_id, user_id=_user_id_from_principal(principal))
        await db.commit()
        return payload
    except McpNotFoundError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except McpServiceError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/mcp/servers/{server_id}/tools", response_model=list[McpDiscoveredToolResponse])
async def get_mcp_server_tools(
    server_id: UUID,
    snapshot_version: int | None = Query(default=None),
    principal: dict = Depends(require_scopes("tools.read")),
    db: AsyncSession = Depends(get_db),
):
    service = McpService(db, _organization_id_from_principal(principal))
    try:
        tools = await service.get_server_tools(server_id, snapshot_version=snapshot_version)
        return [_serialize_tool(tool) for tool in tools]
    except McpNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/mcp/servers/{server_id}/auth/start", response_model=McpAuthStartResponse)
async def start_mcp_auth(
    server_id: UUID,
    principal: dict = Depends(require_scopes("tools.write")),
    db: AsyncSession = Depends(get_db),
):
    service = McpService(db, _organization_id_from_principal(principal))
    try:
        payload = await service.start_oauth(server_id, user_id=_user_id_from_principal(principal))
        await db.commit()
        return McpAuthStartResponse(**payload)
    except McpNotFoundError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except McpServiceError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/mcp/auth/callback", response_class=HTMLResponse)
async def handle_mcp_auth_callback(
    state: str,
    code: str,
    db: AsyncSession = Depends(get_db),
):
    oauth_state = await db.scalar(select(McpOauthState).where(McpOauthState.state == state))
    if oauth_state is None:
        return HTMLResponse("<html><body>Invalid MCP OAuth state.</body></html>", status_code=400)
    service = McpService(db, oauth_state.organization_id)
    try:
        server, _connection = await service.handle_oauth_callback(state=state, code=code)
        await db.commit()
        return HTMLResponse(service.oauth_callback_html(success=True, message=f"Connected {server.name}."))
    except McpServiceError as exc:
        await db.rollback()
        return HTMLResponse(service.oauth_callback_html(success=False, message=str(exc)), status_code=400)


@router.get("/mcp/oauth/client-metadata/{server_id}")
async def get_mcp_client_metadata_document(
    server_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    server = await db.scalar(select(McpServer).where(McpServer.id == server_id))
    if server is None:
        raise HTTPException(status_code=404, detail="MCP server not found")
    origin = resolve_local_backend_origin().rstrip("/")
    callback_url = f"{origin}/mcp/auth/callback"
    return {
        "client_id": f"{origin}/mcp/oauth/client-metadata/{server_id}",
        "client_name": f"Talmudpedia MCP Client{f' ({server.name})' if server else ''}",
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "redirect_uris": [callback_url],
        "token_endpoint_auth_method": "none",
    }


@router.get("/mcp/servers/{server_id}/account/me", response_model=McpAccountConnectionResponse | None)
async def get_mcp_account_me(
    server_id: UUID,
    principal: dict = Depends(require_scopes("tools.read")),
    db: AsyncSession = Depends(get_db),
):
    service = McpService(db, _organization_id_from_principal(principal))
    connection = await service.get_current_user_connection(server_id, user_id=_user_id_from_principal(principal))
    if connection is None:
        return None
    return _serialize_connection(connection)


@router.delete("/mcp/servers/{server_id}/account/me")
async def delete_mcp_account_me(
    server_id: UUID,
    principal: dict = Depends(require_scopes("tools.write")),
    db: AsyncSession = Depends(get_db),
):
    service = McpService(db, _organization_id_from_principal(principal))
    await service.disconnect_current_user(server_id, user_id=_user_id_from_principal(principal))
    await db.commit()
    return {"ok": True}


@router.post("/agents/{agent_id}/mcp-mounts", response_model=McpAgentMountResponse)
async def create_mcp_mount(
    agent_id: UUID,
    request: McpAgentMountCreateRequest,
    principal: dict = Depends(require_scopes("agents.write")),
    db: AsyncSession = Depends(get_db),
):
    service = McpService(db, _organization_id_from_principal(principal))
    try:
        mount = await service.create_agent_mount(
            agent_id=agent_id,
            server_id=request.server_id,
            created_by=_user_id_from_principal(principal),
            approval_policy=request.approval_policy,
        )
        await db.commit()
        await db.refresh(mount)
        return _serialize_mount(mount)
    except McpNotFoundError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except McpServiceError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/agents/{agent_id}/mcp-mounts", response_model=list[McpAgentMountResponse])
async def list_mcp_mounts(
    agent_id: UUID,
    principal: dict = Depends(require_scopes("agents.read")),
    db: AsyncSession = Depends(get_db),
):
    service = McpService(db, _organization_id_from_principal(principal))
    mounts = await service.list_agent_mounts(agent_id)
    return [_serialize_mount(mount) for mount in mounts]


@router.patch("/agents/{agent_id}/mcp-mounts/{mount_id}", response_model=McpAgentMountResponse)
async def patch_mcp_mount(
    agent_id: UUID,
    mount_id: UUID,
    request: McpAgentMountUpdateRequest,
    principal: dict = Depends(require_scopes("agents.write")),
    db: AsyncSession = Depends(get_db),
):
    _ = agent_id
    service = McpService(db, _organization_id_from_principal(principal))
    try:
        mount = await service.update_agent_mount(mount_id, request.model_dump(exclude_unset=True))
        await db.commit()
        await db.refresh(mount)
        return _serialize_mount(mount)
    except McpNotFoundError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except McpServiceError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/agents/{agent_id}/mcp-mounts/{mount_id}")
async def delete_mcp_mount(
    agent_id: UUID,
    mount_id: UUID,
    principal: dict = Depends(require_scopes("agents.write")),
    db: AsyncSession = Depends(get_db),
):
    _ = agent_id
    service = McpService(db, _organization_id_from_principal(principal))
    try:
        await service.delete_agent_mount(mount_id)
        await db.commit()
        return {"ok": True}
    except McpNotFoundError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
