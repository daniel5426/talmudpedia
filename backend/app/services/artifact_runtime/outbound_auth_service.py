from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import os
import re
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import ALGORITHM, SECRET_KEY
from app.db.postgres.models.artifact_runtime import ArtifactRevision, ArtifactRun
from app.db.postgres.models.registry import IntegrationCredential, IntegrationCredentialCategory
from app.services.credentials_service import CredentialsService


OUTBOUND_GRANT_AUDIENCE = "artifact-runtime-outbound"
OUTBOUND_GRANT_TTL_SECONDS = 600
SUPPORTED_HTTP_VECTOR_PROVIDERS = {"pinecone", "qdrant"}
CREDENTIAL_REFERENCE_RE = re.compile(r"@\{(?:[^{}|]*\|)?([0-9a-fA-F-]{36})\}")


@dataclass(frozen=True)
class ArtifactProviderPreset:
    auth_mode: str
    header_name: str | None
    header_prefix: str | None
    allowed_hosts: tuple[str, ...]


_PROVIDER_PRESETS: dict[tuple[IntegrationCredentialCategory, str], ArtifactProviderPreset] = {
    (IntegrationCredentialCategory.LLM_PROVIDER, "openai"): ArtifactProviderPreset("bearer", "Authorization", "Bearer ", ("api.openai.com",)),
    (IntegrationCredentialCategory.LLM_PROVIDER, "anthropic"): ArtifactProviderPreset("api_key_header", "x-api-key", None, ("api.anthropic.com",)),
    (IntegrationCredentialCategory.LLM_PROVIDER, "google"): ArtifactProviderPreset("api_key_header", "x-goog-api-key", None, ("generativelanguage.googleapis.com",)),
    (IntegrationCredentialCategory.LLM_PROVIDER, "gemini"): ArtifactProviderPreset("api_key_header", "x-goog-api-key", None, ("generativelanguage.googleapis.com",)),
    (IntegrationCredentialCategory.LLM_PROVIDER, "xai"): ArtifactProviderPreset("bearer", "Authorization", "Bearer ", ("api.x.ai",)),
    (IntegrationCredentialCategory.VECTOR_STORE, "pinecone"): ArtifactProviderPreset("api_key_header", "Api-Key", None, ("api.pinecone.io",)),
    (IntegrationCredentialCategory.VECTOR_STORE, "qdrant"): ArtifactProviderPreset("api_key_header", "api-key", None, ("api.qdrant.io",)),
    (IntegrationCredentialCategory.TOOL_PROVIDER, "serper"): ArtifactProviderPreset("api_key_header", "X-API-KEY", None, ("google.serper.dev",)),
    (IntegrationCredentialCategory.TOOL_PROVIDER, "tavily"): ArtifactProviderPreset("bearer", "Authorization", "Bearer ", ("api.tavily.com",)),
    (IntegrationCredentialCategory.TOOL_PROVIDER, "exa"): ArtifactProviderPreset("api_key_header", "x-api-key", None, ("api.exa.ai",)),
}


class ArtifactOutboundAuthError(RuntimeError):
    pass


def _grant_secret() -> str:
    return (
        str(os.getenv("ARTIFACT_RUNTIME_SHARED_SECRET") or "").strip()
        or str(os.getenv("ARTIFACT_CF_DISPATCH_TOKEN") or "").strip()
        or SECRET_KEY
    )


def extract_credential_ids_from_source_files(source_files: list[dict[str, Any]] | None) -> list[UUID]:
    found: dict[str, UUID] = {}
    for item in list(source_files or []):
        if not isinstance(item, dict):
            continue
        for match in CREDENTIAL_REFERENCE_RE.finditer(str(item.get("content") or "")):
            credential_id = _parse_uuid_or_none(match.group(1))
            if credential_id is not None:
                found[str(credential_id)] = credential_id
    return list(found.values())


async def resolve_outbound_allowed_hosts(
    *,
    db: AsyncSession,
    tenant_id: UUID,
    revision: ArtifactRevision,
    base_allowed_hosts: set[str] | None = None,
) -> list[str]:
    hosts = {
        str(item or "").strip().lower()
        for item in set(base_allowed_hosts or set())
        if str(item or "").strip()
    }
    credentials = CredentialsService(db, tenant_id)
    for credential_id in extract_credential_ids_from_source_files(revision.source_files):
        credential = await credentials.get_by_id(credential_id)
        if credential is None or not credential.is_enabled:
            continue
        hosts.update(_credential_allowed_hosts(credential))
    return sorted(hosts)


def mint_outbound_grant(
    *,
    run: ArtifactRun,
    revision: ArtifactRevision,
) -> str | None:
    credential_ids = [str(item) for item in extract_credential_ids_from_source_files(revision.source_files)]
    if not credential_ids:
        return None
    now = datetime.now(timezone.utc)
    payload = {
        "sub": f"artifact-run:{run.id}",
        "aud": OUTBOUND_GRANT_AUDIENCE,
        "tenant_id": str(run.tenant_id),
        "run_id": str(run.id),
        "revision_id": str(revision.id),
        "credential_ids": credential_ids,
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=OUTBOUND_GRANT_TTL_SECONDS)).timestamp()),
    }
    return jwt.encode(payload, _grant_secret(), algorithm=ALGORITHM)


def decode_outbound_grant(token: str) -> dict[str, Any]:
    if not str(token or "").strip():
        raise ArtifactOutboundAuthError("Missing outbound grant")
    try:
        payload = jwt.decode(
            token,
            _grant_secret(),
            algorithms=[ALGORITHM],
            audience=OUTBOUND_GRANT_AUDIENCE,
        )
    except Exception as exc:
        raise ArtifactOutboundAuthError("Invalid outbound grant") from exc
    if not isinstance(payload, dict):
        raise ArtifactOutboundAuthError("Invalid outbound grant payload")
    return payload


def resolve_credential_reference(value: str) -> UUID:
    text = str(value or "").strip()
    match = CREDENTIAL_REFERENCE_RE.fullmatch(text)
    if match:
        parsed = _parse_uuid_or_none(match.group(1))
        if parsed is not None:
            return parsed
    parsed = _parse_uuid_or_none(text)
    if parsed is not None:
        return parsed
    raise ArtifactOutboundAuthError("Invalid credential reference")


async def resolve_injected_headers(
    *,
    db: AsyncSession,
    grant: str,
    credential_id: str,
    url: str,
) -> dict[str, str]:
    payload = decode_outbound_grant(grant)
    target = urlparse(str(url or "").strip())
    if str(target.scheme or "").strip().lower() not in {"http", "https"}:
        raise ArtifactOutboundAuthError("Invalid outbound URL")
    host = str(target.netloc or "").strip().lower()
    if not host:
        raise ArtifactOutboundAuthError("Invalid outbound URL")

    requested_credential_id = resolve_credential_reference(credential_id)
    allowed_credential_ids = {str(item or "").strip() for item in list(payload.get("credential_ids") or []) if str(item or "").strip()}
    if str(requested_credential_id) not in allowed_credential_ids:
        raise ArtifactOutboundAuthError("Credential is not referenced by this artifact revision")

    run_id = _parse_uuid(payload.get("run_id"), "run_id")
    revision_id = _parse_uuid(payload.get("revision_id"), "revision_id")
    tenant_id = _parse_uuid(payload.get("tenant_id"), "tenant_id")

    run = await db.get(ArtifactRun, run_id)
    if run is None or run.revision_id != revision_id or run.tenant_id != tenant_id:
        raise ArtifactOutboundAuthError("Outbound grant does not match an active artifact run")

    revision = await db.get(ArtifactRevision, revision_id)
    if revision is None:
        raise ArtifactOutboundAuthError("Artifact revision not found")

    credentials = CredentialsService(db, tenant_id)
    credential = await credentials.get_by_id(requested_credential_id)
    if credential is None:
        raise ArtifactOutboundAuthError("Credential not found")
    if not credential.is_enabled:
        raise ArtifactOutboundAuthError("Credential is disabled")

    allowed_hosts = _credential_allowed_hosts(credential)
    if allowed_hosts and host not in allowed_hosts:
        raise ArtifactOutboundAuthError("Outbound host is not allowed for this credential")

    resolved = await credentials.resolve_backend_config(
        {},
        requested_credential_id,
        category=credential.category,
        provider_key=credential.provider_key,
        provider_variant=credential.provider_variant,
    )
    return _build_injected_headers(
        binding=_credential_runtime_config(credential),
        resolved_credentials=resolved,
    )


def _credential_allowed_hosts(credential: IntegrationCredential) -> set[str]:
    config = _credential_runtime_config(credential)
    return {
        str(item or "").strip().lower()
        for item in list(config.get("allowed_hosts") or [])
        if str(item or "").strip()
    }


def _credential_runtime_config(credential: IntegrationCredential) -> dict[str, Any]:
    provider_key = str(credential.provider_key or "").strip().lower()
    category = credential.category
    if category == IntegrationCredentialCategory.VECTOR_STORE and provider_key not in SUPPORTED_HTTP_VECTOR_PROVIDERS:
        raise ArtifactOutboundAuthError(f"Provider '{provider_key}' is not supported for artifact outbound credentials")

    preset = _PROVIDER_PRESETS.get((category, provider_key))
    if preset is not None:
        return {
            "auth_mode": preset.auth_mode,
            "header_name": preset.header_name,
            "header_prefix": preset.header_prefix,
            "allowed_hosts": list(preset.allowed_hosts),
        }

    if category != IntegrationCredentialCategory.CUSTOM:
        raise ArtifactOutboundAuthError(f"Provider '{provider_key}' is not supported for artifact outbound credentials")

    raw_credentials = credential.credentials if isinstance(credential.credentials, dict) else {}
    auth_mode = str(raw_credentials.get("auth_mode") or ("basic" if raw_credentials.get("username") and raw_credentials.get("password") else "custom_header")).strip().lower()
    if auth_mode not in {"bearer", "api_key_header", "basic", "custom_header"}:
        raise ArtifactOutboundAuthError("Unsupported custom credential auth mode")
    header_name = str(raw_credentials.get("header_name") or "").strip() or None
    header_prefix = raw_credentials.get("header_prefix")
    if header_prefix is not None:
        header_prefix = str(header_prefix)
    allowed_hosts = [
        str(item or "").strip().lower()
        for item in list(raw_credentials.get("allowed_hosts") or [])
        if str(item or "").strip()
    ]
    if auth_mode in {"bearer", "basic"} and not header_name:
        header_name = "Authorization"
    if auth_mode in {"api_key_header", "custom_header"} and not header_name:
        raise ArtifactOutboundAuthError("Custom credentials require credentials.header_name")
    return {
        "auth_mode": auth_mode,
        "header_name": header_name,
        "header_prefix": header_prefix,
        "allowed_hosts": allowed_hosts,
    }


def _build_injected_headers(
    *,
    binding: dict[str, Any],
    resolved_credentials: dict[str, Any],
) -> dict[str, str]:
    auth_mode = str(binding.get("auth_mode") or "").strip().lower()
    header_name = str(binding.get("header_name") or "").strip() or "Authorization"
    header_prefix = binding.get("header_prefix")
    if header_prefix is not None:
        header_prefix = str(header_prefix)

    if auth_mode == "basic":
        username = str(resolved_credentials.get("username") or "").strip()
        password = str(resolved_credentials.get("password") or "").strip()
        if not username or not password:
            raise ArtifactOutboundAuthError("Missing username/password for basic auth credential")
        token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        prefix = "Basic " if header_prefix in (None, "") else header_prefix
        return {header_name: f"{prefix}{token}"}

    secret_value = (
        str(resolved_credentials.get("api_key") or "").strip()
        or str(resolved_credentials.get("token") or "").strip()
        or str(resolved_credentials.get("value") or "").strip()
    )
    if not secret_value:
        raise ArtifactOutboundAuthError("Missing or invalid provider credentials")

    if auth_mode == "bearer":
        prefix = "Bearer " if header_prefix in (None, "") else header_prefix
        return {header_name: f"{prefix}{secret_value}"}

    prefix = "" if header_prefix in (None, "") else str(header_prefix)
    return {header_name: f"{prefix}{secret_value}"}


def _parse_uuid_or_none(value: Any) -> UUID | None:
    if value in (None, ""):
        return None
    try:
        return UUID(str(value))
    except Exception:
        return None


def _parse_uuid(value: Any, field: str) -> UUID:
    try:
        return UUID(str(value))
    except Exception as exc:
        raise ArtifactOutboundAuthError(f"Invalid outbound grant field: {field}") from exc
