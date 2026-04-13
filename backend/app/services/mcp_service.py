from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import html
import json
import re
import secrets
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlencode
from uuid import UUID

from sqlalchemy import delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.runtime_urls import resolve_local_backend_origin
from app.db.postgres.models.agents import Agent
from app.db.postgres.models.mcp import (
    McpAccountConnectionStatus,
    McpAgentMount,
    McpApprovalPolicy,
    McpAuthMode,
    McpDiscoveredTool,
    McpOauthState,
    McpServer,
    McpSyncStatus,
    McpUserAccountConnection,
)
from app.services.mcp_client import (
    McpProtocolError,
    McpUnauthorizedError,
    call_mcp_tool,
    discover_mcp_oauth_metadata,
    exchange_oauth_code,
    initialize_mcp_session,
    list_mcp_tools,
    normalize_token_payload,
    refresh_oauth_token,
    register_oauth_client,
    token_expired,
    validate_mcp_server_url,
)
from app.services.mcp_crypto import (
    build_pkce_challenge,
    decrypt_json,
    decrypt_text,
    encrypt_json,
    encrypt_text,
    generate_pkce_verifier,
)


class McpServiceError(Exception):
    pass


class McpNotFoundError(McpServiceError):
    pass


class McpAuthRequiredRuntimeError(McpServiceError):
    def __init__(self, message: str, *, server: McpServer, tool_name: str | None = None):
        super().__init__(message)
        self.server = server
        self.tool_name = tool_name


class McpApprovalRequiredRuntimeError(McpServiceError):
    def __init__(self, message: str, *, mount: McpAgentMount, tool_name: str):
        super().__init__(message)
        self.mount = mount
        self.tool_name = tool_name


class McpToolUnavailableRuntimeError(McpServiceError):
    pass


def _slugify(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "_", str(value or "").strip().lower())
    return re.sub(r"_+", "_", text).strip("_") or "tool"


def _json_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _json_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ResolvedMcpAuth:
    headers: dict[str, str]
    bearer_token: str | None
    auth_identity: str
    account_connection: McpUserAccountConnection | None = None


class McpService:
    def __init__(self, db: AsyncSession, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id

    async def _get_server(self, server_id: UUID) -> McpServer:
        server = await self.db.scalar(
            select(McpServer).where(
                McpServer.id == server_id,
                McpServer.tenant_id == self.tenant_id,
            )
        )
        if server is None:
            raise McpNotFoundError("MCP server not found")
        return server

    async def _find_server_by_normalized_url(self, server_url: str) -> McpServer | None:
        normalized = str(server_url or "").strip().rstrip("/").lower()
        if not normalized:
            return None
        return await self.db.scalar(
            select(McpServer)
            .where(
                McpServer.tenant_id == self.tenant_id,
                func.lower(func.regexp_replace(McpServer.server_url, r"/+$", "")) == normalized,
            )
            .order_by(desc(McpServer.updated_at), McpServer.name.asc())
        )

    async def _get_agent(self, agent_id: UUID) -> Agent:
        agent = await self.db.scalar(
            select(Agent).where(
                Agent.id == agent_id,
                Agent.tenant_id == self.tenant_id,
            )
        )
        if agent is None:
            raise McpNotFoundError("Agent not found")
        return agent

    def _server_secret_payload(self, server: McpServer) -> dict[str, Any]:
        payload = {
            "name": server.name,
            "description": server.description,
            "server_url": server.server_url,
            "transport": server.transport,
            "auth_mode": server.auth_mode,
            "is_active": bool(server.is_active),
            "auth_config": _json_dict(server.auth_config),
            "auth_metadata": _json_dict(server.auth_metadata),
            "capability_snapshot": _json_dict(server.capability_snapshot),
            "oauth_client_id": server.oauth_client_id,
            "oauth_client_registration": _json_dict(server.oauth_client_registration),
            "oauth_client_secret_expires_at": server.oauth_client_secret_expires_at,
            "tool_snapshot_version": int(server.tool_snapshot_version or 0),
            "sync_status": server.sync_status,
            "sync_error": server.sync_error,
            "last_tested_at": server.last_tested_at,
            "last_synced_at": server.last_synced_at,
            "created_at": server.created_at,
            "updated_at": server.updated_at,
            "has_static_bearer_token": bool(server.static_bearer_token_encrypted),
            "has_static_headers": bool(server.static_headers_encrypted),
            "has_oauth_client_secret": bool(server.oauth_client_secret_encrypted),
        }
        return payload

    async def list_servers(self) -> list[McpServer]:
        result = await self.db.execute(
            select(McpServer)
            .where(McpServer.tenant_id == self.tenant_id)
            .order_by(desc(McpServer.updated_at), McpServer.name.asc())
        )
        return list(result.scalars().all())

    async def create_server(self, payload: dict[str, Any], *, created_by: UUID | None) -> McpServer:
        try:
            server_url = await validate_mcp_server_url(
                str(payload.get("server_url") or "").strip(),
                for_auth=str(payload.get("auth_mode") or "").strip().lower() == McpAuthMode.OAUTH_USER_ACCOUNT.value,
            )
        except ValueError as exc:
            raise McpServiceError(str(exc)) from exc
        existing = await self._find_server_by_normalized_url(server_url)
        if existing is not None:
            existing.is_active = bool(payload.get("is_active", True))
            await self.db.flush()
            return existing
        server = McpServer(
            tenant_id=self.tenant_id,
            created_by=created_by,
            name=str(payload.get("name") or "").strip(),
            description=str(payload.get("description") or "").strip() or None,
            server_url=server_url,
            transport="streamable_http",
            auth_mode=str(payload.get("auth_mode") or McpAuthMode.NONE.value).strip().lower(),
            auth_config=_json_dict(payload.get("auth_config")),
            static_bearer_token_encrypted=encrypt_text(payload.get("static_bearer_token")),
            static_headers_encrypted=encrypt_json(payload.get("static_headers")),
            oauth_client_id=str(payload.get("oauth_client_id") or "").strip() or None,
            oauth_client_secret_encrypted=encrypt_text(payload.get("oauth_client_secret")),
            is_active=bool(payload.get("is_active", True)),
        )
        if not server.name:
            raise McpServiceError("name is required")
        self.db.add(server)
        await self.db.flush()
        return server

    async def update_server(self, server_id: UUID, payload: dict[str, Any]) -> McpServer:
        server = await self._get_server(server_id)
        if "name" in payload:
            server.name = str(payload.get("name") or "").strip() or server.name
        if "description" in payload:
            server.description = str(payload.get("description") or "").strip() or None
        if "server_url" in payload:
            try:
                server.server_url = await validate_mcp_server_url(
                    str(payload.get("server_url") or "").strip(),
                    for_auth=(payload.get("auth_mode") or server.auth_mode) == McpAuthMode.OAUTH_USER_ACCOUNT.value,
                )
            except ValueError as exc:
                raise McpServiceError(str(exc)) from exc
        if "auth_mode" in payload:
            server.auth_mode = str(payload.get("auth_mode") or McpAuthMode.NONE.value).strip().lower()
        if "auth_config" in payload:
            server.auth_config = _json_dict(payload.get("auth_config"))
        if "static_bearer_token" in payload:
            server.static_bearer_token_encrypted = encrypt_text(payload.get("static_bearer_token"))
        if "static_headers" in payload:
            server.static_headers_encrypted = encrypt_json(payload.get("static_headers"))
        if "oauth_client_id" in payload:
            server.oauth_client_id = str(payload.get("oauth_client_id") or "").strip() or None
        if "oauth_client_secret" in payload:
            server.oauth_client_secret_encrypted = encrypt_text(payload.get("oauth_client_secret"))
        if "is_active" in payload:
            server.is_active = bool(payload.get("is_active"))
        await self.db.flush()
        return server

    async def get_server_tools(self, server_id: UUID, *, snapshot_version: int | None = None) -> list[McpDiscoveredTool]:
        server = await self._get_server(server_id)
        version = int(snapshot_version if snapshot_version is not None else server.tool_snapshot_version or 0)
        if version <= 0:
            return []
        result = await self.db.execute(
            select(McpDiscoveredTool)
            .where(
                McpDiscoveredTool.server_id == server.id,
                McpDiscoveredTool.snapshot_version == version,
            )
            .order_by(McpDiscoveredTool.name.asc())
        )
        return list(result.scalars().all())

    async def _resolve_shared_auth(self, server: McpServer) -> ResolvedMcpAuth:
        headers = decrypt_json(server.static_headers_encrypted) or {}
        bearer_token = decrypt_text(server.static_bearer_token_encrypted)
        return ResolvedMcpAuth(
            headers=headers if isinstance(headers, dict) else {},
            bearer_token=bearer_token,
            auth_identity=f"server:{server.id}",
        )

    async def _get_user_connection(self, server_id: UUID, user_id: UUID) -> McpUserAccountConnection | None:
        return await self.db.scalar(
            select(McpUserAccountConnection).where(
                McpUserAccountConnection.server_id == server_id,
                McpUserAccountConnection.user_id == user_id,
                McpUserAccountConnection.tenant_id == self.tenant_id,
            )
        )

    async def get_current_user_connection(self, server_id: UUID, *, user_id: UUID) -> McpUserAccountConnection | None:
        await self._get_server(server_id)
        return await self._get_user_connection(server_id, user_id)

    async def disconnect_current_user(self, server_id: UUID, *, user_id: UUID) -> None:
        await self._get_server(server_id)
        await self.db.execute(
            delete(McpUserAccountConnection).where(
                McpUserAccountConnection.server_id == server_id,
                McpUserAccountConnection.user_id == user_id,
                McpUserAccountConnection.tenant_id == self.tenant_id,
            )
        )

    async def _refresh_user_connection_if_needed(
        self,
        *,
        server: McpServer,
        connection: McpUserAccountConnection,
    ) -> McpUserAccountConnection:
        token_payload = decrypt_json(connection.token_payload_encrypted) or {}
        if not token_expired(token_payload):
            return connection
        refresh_token = str(token_payload.get("refresh_token") or "").strip()
        if not refresh_token:
            connection.status = McpAccountConnectionStatus.STALE.value
            connection.last_error = "Missing refresh token"
            await self.db.flush()
            raise McpAuthRequiredRuntimeError("MCP account link expired", server=server)

        auth_metadata = _json_dict(server.auth_metadata)
        auth_server_metadata = _json_dict(auth_metadata.get("authorization_server_metadata"))
        token_endpoint = str(auth_server_metadata.get("token_endpoint") or "").strip()
        if not token_endpoint:
            connection.status = McpAccountConnectionStatus.STALE.value
            connection.last_error = "Missing token endpoint metadata"
            await self.db.flush()
            raise McpAuthRequiredRuntimeError("MCP account link expired", server=server)

        client_id = server.oauth_client_id
        client_secret = decrypt_text(server.oauth_client_secret_encrypted)
        if not client_id:
            registration = _json_dict(server.oauth_client_registration)
            client_id = str(registration.get("client_id") or "").strip() or None
            if not client_secret:
                client_secret = str(registration.get("client_secret") or "").strip() or None
        if not client_id:
            raise McpAuthRequiredRuntimeError("MCP OAuth client is not configured", server=server)

        try:
            refreshed = await refresh_oauth_token(
                token_endpoint=token_endpoint,
                refresh_token=refresh_token,
                client_id=client_id,
                client_secret=client_secret,
            )
        except Exception as exc:
            connection.status = McpAccountConnectionStatus.STALE.value
            connection.last_error = str(exc)
            await self.db.flush()
            raise McpAuthRequiredRuntimeError("MCP account link expired", server=server) from exc

        normalized = normalize_token_payload(refreshed, previous=token_payload)
        connection.token_payload_encrypted = encrypt_json(normalized)
        connection.status = McpAccountConnectionStatus.ACTIVE.value
        connection.last_error = None
        connection.last_refreshed_at = _utcnow()
        connection.access_token_expires_at = self._token_expiry(normalized)
        connection.refresh_token_expires_at = self._refresh_expiry(normalized)
        await self.db.flush()
        return connection

    def _token_expiry(self, token_payload: dict[str, Any]) -> datetime | None:
        raw = token_payload.get("expires_at")
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except Exception:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    def _refresh_expiry(self, token_payload: dict[str, Any]) -> datetime | None:
        raw = token_payload.get("refresh_token_expires_at")
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except Exception:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    async def resolve_server_runtime_auth(
        self,
        *,
        server: McpServer,
        user_id: UUID | None,
    ) -> ResolvedMcpAuth:
        auth_mode = str(server.auth_mode or McpAuthMode.NONE.value).strip().lower()
        if auth_mode in {McpAuthMode.NONE.value, McpAuthMode.STATIC_BEARER.value, McpAuthMode.STATIC_HEADERS.value}:
            return await self._resolve_shared_auth(server)
        if auth_mode != McpAuthMode.OAUTH_USER_ACCOUNT.value:
            raise McpServiceError(f"Unsupported MCP auth mode: {auth_mode}")
        if user_id is None:
            raise McpAuthRequiredRuntimeError("This MCP server requires a linked user account", server=server)
        connection = await self._get_user_connection(server.id, user_id)
        if connection is None or connection.status != McpAccountConnectionStatus.ACTIVE.value:
            raise McpAuthRequiredRuntimeError("Connect your account to use this MCP server", server=server)
        connection = await self._refresh_user_connection_if_needed(server=server, connection=connection)
        token_payload = decrypt_json(connection.token_payload_encrypted) or {}
        bearer_token = str(token_payload.get("access_token") or "").strip()
        if not bearer_token:
            raise McpAuthRequiredRuntimeError("Connect your account to use this MCP server", server=server)
        connection.last_used_at = _utcnow()
        await self.db.flush()
        return ResolvedMcpAuth(
            headers={},
            bearer_token=bearer_token,
            auth_identity=f"user:{user_id}",
            account_connection=connection,
        )

    async def test_server(self, server_id: UUID) -> dict[str, Any]:
        server = await self._get_server(server_id)
        try:
            auth = await self.resolve_server_runtime_auth(server=server, user_id=None)
        except McpAuthRequiredRuntimeError:
            auth = ResolvedMcpAuth(headers={}, bearer_token=None, auth_identity=f"server:{server.id}")

        try:
            init = await initialize_mcp_session(
                server_url=server.server_url,
                headers=auth.headers,
                bearer_token=auth.bearer_token,
                auth_identity=auth.auth_identity,
            )
            server.capability_snapshot = init.capabilities
            server.sync_status = McpSyncStatus.READY.value
            server.sync_error = None
            server.last_tested_at = _utcnow()
            await self.db.flush()
            return {
                "status": "ok",
                "protocol_version": init.protocol_version,
                "server_info": init.server_info,
                "capabilities": init.capabilities,
            }
        except McpUnauthorizedError as exc:
            try:
                metadata = await discover_mcp_oauth_metadata(server_url=server.server_url, challenge_header=exc.www_authenticate)
            except ValueError as metadata_exc:
                raise McpServiceError(str(metadata_exc)) from metadata_exc
            server.auth_metadata = metadata
            server.sync_status = McpSyncStatus.AUTH_REQUIRED.value
            server.sync_error = None
            server.last_tested_at = _utcnow()
            await self.db.flush()
            return {"status": "auth_required", "auth_metadata": metadata}
        except McpProtocolError as exc:
            server.sync_status = McpSyncStatus.ERROR.value
            server.sync_error = str(exc)
            server.last_tested_at = _utcnow()
            await self.db.flush()
            raise McpServiceError(str(exc)) from exc
        except Exception as exc:
            server.sync_status = McpSyncStatus.ERROR.value
            server.sync_error = str(exc)
            server.last_tested_at = _utcnow()
            await self.db.flush()
            raise McpServiceError(f"MCP test failed: {exc}") from exc

    async def sync_server(self, server_id: UUID, *, user_id: UUID | None = None) -> dict[str, Any]:
        server = await self._get_server(server_id)
        auth = await self.resolve_server_runtime_auth(server=server, user_id=user_id)
        try:
            response = await list_mcp_tools(
                server_url=server.server_url,
                headers=auth.headers,
                bearer_token=auth.bearer_token,
                auth_identity=auth.auth_identity,
            )
        except McpUnauthorizedError as exc:
            try:
                metadata = await discover_mcp_oauth_metadata(server_url=server.server_url, challenge_header=exc.www_authenticate)
            except ValueError as metadata_exc:
                raise McpServiceError(str(metadata_exc)) from metadata_exc
            server.auth_metadata = metadata
            server.sync_status = McpSyncStatus.AUTH_REQUIRED.value
            server.sync_error = None
            await self.db.flush()
            raise McpAuthRequiredRuntimeError("Connect your account to sync this MCP server", server=server) from exc
        except McpProtocolError as exc:
            server.sync_status = McpSyncStatus.ERROR.value
            server.sync_error = str(exc)
            await self.db.flush()
            raise McpServiceError(str(exc)) from exc
        except Exception as exc:
            server.sync_status = McpSyncStatus.ERROR.value
            server.sync_error = str(exc)
            await self.db.flush()
            raise McpServiceError(f"MCP sync failed: {exc}") from exc

        server.tool_snapshot_version = int(server.tool_snapshot_version or 0) + 1
        server.sync_status = McpSyncStatus.READY.value
        server.sync_error = None
        server.last_synced_at = _utcnow()
        server.capability_snapshot = response["initialize"].capabilities

        version = server.tool_snapshot_version
        for item in response.get("tools", []):
            if not isinstance(item, dict):
                continue
            discovered = McpDiscoveredTool(
                tenant_id=self.tenant_id,
                server_id=server.id,
                snapshot_version=version,
                name=str(item.get("name") or "").strip(),
                title=str(item.get("title") or "").strip() or None,
                description=str(item.get("description") or "").strip() or None,
                input_schema=_json_dict(item.get("inputSchema")),
                annotations=_json_dict(item.get("annotations")),
                tool_metadata=_json_dict(item),
            )
            if discovered.name:
                self.db.add(discovered)
        await self.db.flush()
        return {"snapshot_version": version, "tool_count": len(response.get("tools", []))}

    async def ensure_oauth_metadata(self, server: McpServer) -> dict[str, Any]:
        metadata = _json_dict(server.auth_metadata)
        auth_server_metadata = _json_dict(metadata.get("authorization_server_metadata"))
        authorization_endpoint = str(auth_server_metadata.get("authorization_endpoint") or "").strip()
        token_endpoint = str(auth_server_metadata.get("token_endpoint") or "").strip()
        if auth_server_metadata and authorization_endpoint and token_endpoint:
            return metadata
        try:
            await initialize_mcp_session(
                server_url=server.server_url,
                headers={},
                bearer_token=None,
                auth_identity=f"server:{server.id}",
            )
        except McpUnauthorizedError as exc:
            try:
                metadata = await discover_mcp_oauth_metadata(server_url=server.server_url, challenge_header=exc.www_authenticate)
            except ValueError as metadata_exc:
                raise McpServiceError(str(metadata_exc)) from metadata_exc
            server.auth_metadata = metadata
            await self.db.flush()
            return metadata
        raise McpServiceError("MCP server did not advertise OAuth authorization metadata")

    async def _resolve_oauth_client(
        self,
        *,
        server: McpServer,
        auth_metadata: dict[str, Any],
    ) -> tuple[str, str | None, str | None]:
        auth_server_metadata = _json_dict(auth_metadata.get("authorization_server_metadata"))
        token_method = str(server.auth_config.get("token_endpoint_auth_method") or "").strip() or None

        if server.oauth_client_id:
            return server.oauth_client_id, decrypt_text(server.oauth_client_secret_encrypted), token_method

        registration = _json_dict(server.oauth_client_registration)
        registration_client_id = str(registration.get("client_id") or "").strip()
        if registration_client_id:
            return registration_client_id, str(registration.get("client_secret") or "").strip() or None, token_method

        callback_url = f"{resolve_local_backend_origin().rstrip('/')}/mcp/auth/callback"
        if bool(auth_server_metadata.get("client_id_metadata_document_supported")):
            return self.build_client_metadata_document_url(server.id), None, "none"

        registration_endpoint = str(auth_server_metadata.get("registration_endpoint") or "").strip()
        if registration_endpoint:
            try:
                registered = await register_oauth_client(
                    registration_endpoint=registration_endpoint,
                    payload={
                        "client_name": f"Talmudpedia MCP Client ({server.name})",
                        "redirect_uris": [callback_url],
                        "grant_types": ["authorization_code", "refresh_token"],
                        "response_types": ["code"],
                        "token_endpoint_auth_method": "none",
                    },
                )
            except Exception as exc:
                raise McpServiceError(
                    "Dynamic OAuth client registration failed for this MCP server. "
                    "Configure OAuth client credentials manually and try again."
                ) from exc
            server.oauth_client_registration = registered
            await self.db.flush()
            return str(registered["client_id"]), str(registered.get("client_secret") or "").strip() or None, "none"

        raise McpServiceError("This MCP server requires admin-configured OAuth client credentials")

    def build_client_metadata_document_url(self, server_id: UUID) -> str:
        return f"{resolve_local_backend_origin().rstrip('/')}/mcp/oauth/client-metadata/{server_id}"

    async def start_oauth(self, server_id: UUID, *, user_id: UUID) -> dict[str, Any]:
        server = await self._get_server(server_id)
        if server.auth_mode != McpAuthMode.OAUTH_USER_ACCOUNT.value:
            raise McpServiceError("This MCP server is not configured for user-account OAuth")
        auth_metadata = await self.ensure_oauth_metadata(server)
        protected_resource = _json_dict(auth_metadata.get("protected_resource_metadata"))
        auth_server_metadata = _json_dict(auth_metadata.get("authorization_server_metadata"))
        authorization_endpoint = str(auth_server_metadata.get("authorization_endpoint") or "").strip()
        if not authorization_endpoint:
            raise McpServiceError("Authorization endpoint is missing from MCP auth metadata")

        client_id, client_secret, token_method = await self._resolve_oauth_client(
            server=server,
            auth_metadata=auth_metadata,
        )
        callback_url = f"{resolve_local_backend_origin().rstrip('/')}/mcp/auth/callback"
        verifier = generate_pkce_verifier()
        state_token = secrets.token_urlsafe(32)
        scopes = _json_list(server.auth_config.get("scopes")) or _json_list(protected_resource.get("scopes_supported")) or ["mcp:tools"]

        oauth_state = McpOauthState(
            tenant_id=self.tenant_id,
            server_id=server.id,
            user_id=user_id,
            state=state_token,
            code_verifier=verifier,
            redirect_uri=callback_url,
            client_id=client_id,
            requested_scopes=scopes,
            auth_server_metadata=auth_server_metadata,
            token_method=token_method,
            expires_at=_utcnow() + timedelta(minutes=15),
        )
        self.db.add(oauth_state)
        await self.db.flush()

        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": callback_url,
            "scope": " ".join(str(scope) for scope in scopes if scope),
            "state": state_token,
            "code_challenge": build_pkce_challenge(verifier),
            "code_challenge_method": "S256",
            "resource": server.server_url,
        }
        if client_secret:
            server.oauth_client_secret_encrypted = encrypt_text(client_secret)

        return {"authorization_url": f"{authorization_endpoint}?{urlencode(params)}"}

    async def handle_oauth_callback(self, *, state: str, code: str) -> tuple[McpServer, McpUserAccountConnection]:
        oauth_state = await self.db.scalar(select(McpOauthState).where(McpOauthState.state == state))
        if oauth_state is None:
            raise McpServiceError("Invalid OAuth state")
        if oauth_state.consumed_at is not None:
            raise McpServiceError("OAuth state was already consumed")
        if oauth_state.expires_at <= _utcnow():
            raise McpServiceError("OAuth state expired")

        server = await self._get_server(oauth_state.server_id)
        auth_server_metadata = _json_dict(oauth_state.auth_server_metadata)
        token_endpoint = str(auth_server_metadata.get("token_endpoint") or "").strip()
        if not token_endpoint:
            raise McpServiceError("Token endpoint is missing from authorization server metadata")

        client_secret = decrypt_text(server.oauth_client_secret_encrypted)
        if not client_secret:
            registration = _json_dict(server.oauth_client_registration)
            client_secret = str(registration.get("client_secret") or "").strip() or None

        token_payload = await exchange_oauth_code(
            token_endpoint=token_endpoint,
            code=code,
            code_verifier=oauth_state.code_verifier,
            redirect_uri=oauth_state.redirect_uri,
            client_id=oauth_state.client_id,
            client_secret=client_secret,
        )
        normalized = normalize_token_payload(token_payload)

        connection = await self._get_user_connection(server.id, oauth_state.user_id)
        if connection is None:
            connection = McpUserAccountConnection(
                tenant_id=self.tenant_id,
                server_id=server.id,
                user_id=oauth_state.user_id,
            )
            self.db.add(connection)

        connection.status = McpAccountConnectionStatus.ACTIVE.value
        connection.token_payload_encrypted = encrypt_json(normalized)
        connection.scopes = str(token_payload.get("scope") or "").split() if token_payload.get("scope") else list(
            oauth_state.requested_scopes or []
        )
        connection.account_metadata = {
            "token_type": token_payload.get("token_type"),
            "scope": token_payload.get("scope"),
        }
        connection.last_error = None
        connection.access_token_expires_at = self._token_expiry(normalized)
        connection.refresh_token_expires_at = self._refresh_expiry(normalized)
        connection.last_refreshed_at = _utcnow()

        oauth_state.consumed_at = _utcnow()
        await self.db.flush()
        return server, connection

    def oauth_callback_html(self, *, success: bool, message: str) -> str:
        safe_message = html.escape(message)
        title = "MCP Account Connected" if success else "MCP Account Connection Failed"
        return f"""
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>{title}</title>
    <style>
      body {{ font-family: sans-serif; padding: 32px; color: #111827; }}
      .box {{ max-width: 540px; margin: 0 auto; border: 1px solid #e5e7eb; border-radius: 12px; padding: 24px; }}
      h1 {{ margin: 0 0 12px; font-size: 22px; }}
      p {{ margin: 0; line-height: 1.5; }}
    </style>
  </head>
  <body>
    <div class="box">
      <h1>{title}</h1>
      <p>{safe_message}</p>
    </div>
    <script>
      try {{
        if (window.opener) {{
          window.opener.postMessage({json.dumps({"type": "mcp-oauth-complete", "success": success})}, "*");
          window.close();
        }}
      }} catch (err) {{}}
    </script>
  </body>
</html>
"""

    async def list_agent_mounts(self, agent_id: UUID) -> list[McpAgentMount]:
        await self._get_agent(agent_id)
        result = await self.db.execute(
            select(McpAgentMount)
            .where(
                McpAgentMount.agent_id == agent_id,
                McpAgentMount.tenant_id == self.tenant_id,
            )
            .order_by(McpAgentMount.created_at.asc())
        )
        return list(result.scalars().all())

    async def create_agent_mount(
        self,
        *,
        agent_id: UUID,
        server_id: UUID,
        created_by: UUID | None,
        approval_policy: str | None = None,
    ) -> McpAgentMount:
        await self._get_agent(agent_id)
        server = await self._get_server(server_id)
        if int(server.tool_snapshot_version or 0) <= 0:
            raise McpServiceError("Sync the MCP server before attaching it to an agent")
        mount = McpAgentMount(
            tenant_id=self.tenant_id,
            agent_id=agent_id,
            server_id=server.id,
            created_by=created_by,
            approval_policy=str(approval_policy or McpApprovalPolicy.ASK.value).strip().lower(),
            applied_snapshot_version=int(server.tool_snapshot_version or 0),
            tool_filters={},
            is_active=True,
        )
        self.db.add(mount)
        await self.db.flush()
        return mount

    async def update_agent_mount(self, mount_id: UUID, payload: dict[str, Any]) -> McpAgentMount:
        mount = await self.db.scalar(
            select(McpAgentMount).where(
                McpAgentMount.id == mount_id,
                McpAgentMount.tenant_id == self.tenant_id,
            )
        )
        if mount is None:
            raise McpNotFoundError("MCP agent mount not found")
        if "approval_policy" in payload:
            mount.approval_policy = str(payload.get("approval_policy") or McpApprovalPolicy.ASK.value).strip().lower()
        if "is_active" in payload:
            mount.is_active = bool(payload.get("is_active"))
        if payload.get("apply_latest_snapshot"):
            server = await self._get_server(mount.server_id)
            mount.applied_snapshot_version = int(server.tool_snapshot_version or 0)
        await self.db.flush()
        return mount

    async def delete_agent_mount(self, mount_id: UUID) -> None:
        mount = await self.db.scalar(
            select(McpAgentMount).where(
                McpAgentMount.id == mount_id,
                McpAgentMount.tenant_id == self.tenant_id,
            )
        )
        if mount is None:
            raise McpNotFoundError("MCP agent mount not found")
        await self.db.delete(mount)


class McpRuntimeService:
    def __init__(self, db: AsyncSession, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.mcp = McpService(db, tenant_id)

    def _virtual_tool_id(self, mount_id: UUID, tool_name: str) -> str:
        return f"mcp:{mount_id}:{tool_name}"

    async def list_agent_tools(self, *, agent_id: UUID, user_id: UUID | None) -> list[SimpleNamespace]:
        _ = user_id
        mounts_result = await self.db.execute(
            select(McpAgentMount, McpServer)
            .join(McpServer, McpServer.id == McpAgentMount.server_id)
            .where(
                McpAgentMount.agent_id == agent_id,
                McpAgentMount.tenant_id == self.tenant_id,
                McpAgentMount.is_active == True,
                McpServer.is_active == True,
            )
            .order_by(McpAgentMount.created_at.asc())
        )
        virtual_tools: list[SimpleNamespace] = []
        for mount, server in mounts_result.all():
            tools_result = await self.db.execute(
                select(McpDiscoveredTool)
                .where(
                    McpDiscoveredTool.server_id == server.id,
                    McpDiscoveredTool.snapshot_version == mount.applied_snapshot_version,
                )
                .order_by(McpDiscoveredTool.name.asc())
            )
            for tool in tools_result.scalars().all():
                tool_name = str(tool.name or "").strip()
                if not tool_name:
                    continue
                server_slug = _slugify(server.name)
                tool_slug = _slugify(tool_name)
                virtual_tools.append(
                    SimpleNamespace(
                        id=self._virtual_tool_id(mount.id, tool_name),
                        name=tool.title or tool_name,
                        slug=f"mcp_{server_slug}_{tool_slug}",
                        description=tool.description or f"MCP tool from {server.name}",
                        schema={"input": _json_dict(tool.input_schema), "output": {}},
                        config_schema={
                            "implementation": {
                                "type": "mcp_mount",
                                "server_id": str(server.id),
                                "mount_id": str(mount.id),
                                "tool_name": tool_name,
                            },
                            "execution": {"timeout_s": 60, "is_pure": False, "concurrency_group": f"mcp:{server.id}"},
                        },
                        implementation_type="mcp",
                        is_active=True,
                        status="published",
                        server_name=server.name,
                        mcp_mount_id=str(mount.id),
                        mcp_server_id=str(server.id),
                        mcp_tool_name=tool_name,
                        mcp_virtual=True,
                    )
                )
        return virtual_tools

    async def resolve_virtual_tool(self, tool_id: str) -> tuple[McpAgentMount, McpServer, McpDiscoveredTool]:
        if not str(tool_id).startswith("mcp:"):
            raise McpToolUnavailableRuntimeError("Not an MCP virtual tool id")
        _, raw_mount_id, tool_name = str(tool_id).split(":", 2)
        mount_id = UUID(raw_mount_id)
        row = await self.db.execute(
            select(McpAgentMount, McpServer)
            .join(McpServer, McpServer.id == McpAgentMount.server_id)
            .where(
                McpAgentMount.id == mount_id,
                McpAgentMount.tenant_id == self.tenant_id,
                McpAgentMount.is_active == True,
            )
        )
        joined = row.first()
        if joined is None:
            raise McpToolUnavailableRuntimeError("Mounted MCP server was not found")
        mount, server = joined
        tool = await self.db.scalar(
            select(McpDiscoveredTool).where(
                McpDiscoveredTool.server_id == server.id,
                McpDiscoveredTool.snapshot_version == mount.applied_snapshot_version,
                McpDiscoveredTool.name == tool_name,
            )
        )
        if tool is None:
            raise McpToolUnavailableRuntimeError("MCP tool is no longer available for this mount. Re-sync and re-apply.")
        return mount, server, tool

    async def execute_virtual_tool(
        self,
        *,
        tool_id: str,
        arguments: dict[str, Any],
        user_id: UUID | None,
    ) -> dict[str, Any]:
        mount, server, tool = await self.resolve_virtual_tool(tool_id)
        if mount.approval_policy == McpApprovalPolicy.ASK.value:
            raise McpApprovalRequiredRuntimeError(
                "This MCP tool requires approval before execution",
                mount=mount,
                tool_name=tool.name,
            )
        auth = await self.mcp.resolve_server_runtime_auth(server=server, user_id=user_id)
        result = await call_mcp_tool(
            server_url=server.server_url,
            tool_name=tool.name,
            arguments=arguments,
            headers=auth.headers,
            bearer_token=auth.bearer_token,
            auth_identity=auth.auth_identity,
            timeout_s=60,
        )
        return result
