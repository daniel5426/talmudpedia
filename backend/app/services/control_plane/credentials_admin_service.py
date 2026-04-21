from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.rag import KnowledgeStore
from app.db.postgres.models.registry import (
    IntegrationCredential,
    IntegrationCredentialCategory,
    ModelProviderBinding,
    ModelRegistry,
    ToolRegistry,
)
from app.services.control_plane.context import ControlPlaneContext
from app.services.control_plane.errors import not_found, validation
from app.services.credentials_service import CredentialsService
from app.services.integration_provider_catalog import is_provider_key_allowed


def normalize_provider_key(category: IntegrationCredentialCategory, provider_key: str) -> str:
    key = (provider_key or "").strip().lower()
    if not key:
        raise validation("provider_key is required")
    if not is_provider_key_allowed(category, key):
        raise validation(f"Unsupported provider_key '{provider_key}' for category '{category.value}'")
    return key


def serialize_credential(credential: IntegrationCredential, *, view: str = "full") -> dict[str, Any]:
    payload = {
        "id": str(credential.id),
        "category": getattr(credential.category, "value", credential.category),
        "provider_key": credential.provider_key,
        "provider_variant": credential.provider_variant,
        "display_name": credential.display_name,
        "is_enabled": bool(credential.is_enabled),
        "is_default": bool(credential.is_default),
        "created_at": credential.created_at.isoformat() if credential.created_at else None,
        "updated_at": credential.updated_at.isoformat() if credential.updated_at else None,
    }
    if view == "summary":
        return payload
    payload.update(
        {
            "organization_id": str(credential.organization_id) if credential.organization_id else None,
            "credential_keys": list((credential.credentials or {}).keys()),
        }
    )
    return payload


class CredentialsAdminService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_credentials(
        self,
        *,
        ctx: ControlPlaneContext,
        category: IntegrationCredentialCategory | None = None,
    ) -> list[IntegrationCredential]:
        stmt = select(IntegrationCredential).where(IntegrationCredential.organization_id == ctx.organization_id)
        if category is not None:
            stmt = stmt.where(IntegrationCredential.category == category)
        stmt = stmt.order_by(IntegrationCredential.provider_key.asc(), IntegrationCredential.display_name.asc())
        return list((await self.db.execute(stmt)).scalars().all())

    async def create_credential(
        self,
        *,
        ctx: ControlPlaneContext,
        category: IntegrationCredentialCategory,
        provider_key: str,
        provider_variant: str | None,
        display_name: str,
        credentials: dict[str, Any],
        is_enabled: bool,
        is_default: bool,
    ) -> IntegrationCredential:
        credential = IntegrationCredential(
            organization_id=ctx.organization_id,
            category=category,
            provider_key=normalize_provider_key(category, provider_key),
            provider_variant=provider_variant,
            display_name=display_name,
            credentials=credentials or {},
            is_enabled=is_enabled,
            is_default=is_default,
        )
        self.db.add(credential)
        with self.db.no_autoflush:
            await CredentialsService(self.db, ctx.organization_id).enforce_single_default(credential)
        await self.db.commit()
        await self.db.refresh(credential)
        return credential

    async def update_credential(
        self,
        *,
        ctx: ControlPlaneContext,
        credential_id: UUID,
        patch: dict[str, Any],
    ) -> IntegrationCredential:
        stmt = select(IntegrationCredential).where(
            and_(IntegrationCredential.id == credential_id, IntegrationCredential.organization_id == ctx.organization_id)
        )
        credential = (await self.db.execute(stmt)).scalar_one_or_none()
        if credential is None:
            raise not_found("Credential not found")
        if patch.get("category") is not None:
            credential.category = patch["category"]
            if patch.get("provider_key") is None:
                credential.provider_key = normalize_provider_key(credential.category, credential.provider_key)
        if patch.get("provider_key") is not None:
            effective_category = patch.get("category") or credential.category
            credential.provider_key = normalize_provider_key(effective_category, patch["provider_key"])
        if "provider_variant" in patch:
            credential.provider_variant = patch["provider_variant"]
        if patch.get("display_name") is not None:
            credential.display_name = patch["display_name"]
        if patch.get("credentials") is not None:
            credential.credentials = patch["credentials"]
        if patch.get("is_enabled") is not None:
            credential.is_enabled = patch["is_enabled"]
        if patch.get("is_default") is not None:
            credential.is_default = patch["is_default"]
        with self.db.no_autoflush:
            await CredentialsService(self.db, ctx.organization_id).enforce_single_default(credential)
        await self.db.commit()
        await self.db.refresh(credential)
        return credential

    async def get_usage(self, *, ctx: ControlPlaneContext, credential_id: UUID) -> dict[str, Any]:
        model_rows = (
            await self.db.execute(
                select(
                    ModelProviderBinding.id,
                    ModelProviderBinding.model_id,
                    ModelRegistry.name,
                    ModelProviderBinding.provider,
                    ModelProviderBinding.provider_model_id,
                )
                .join(ModelRegistry, ModelRegistry.id == ModelProviderBinding.model_id)
                .where(
                    ModelProviderBinding.organization_id == ctx.organization_id,
                    ModelProviderBinding.credentials_ref == credential_id,
                )
                .order_by(ModelRegistry.name.asc(), ModelProviderBinding.provider_model_id.asc())
            )
        ).all()
        store_rows = (
            await self.db.execute(
                select(KnowledgeStore.id, KnowledgeStore.name, KnowledgeStore.backend)
                .where(KnowledgeStore.organization_id == ctx.organization_id, KnowledgeStore.credentials_ref == credential_id)
                .order_by(KnowledgeStore.name.asc())
            )
        ).all()
        tool_rows = (
            await self.db.execute(
                select(ToolRegistry.id, ToolRegistry.name, ToolRegistry.builtin_key, ToolRegistry.implementation_type, ToolRegistry.config_schema)
                .where(ToolRegistry.organization_id == ctx.organization_id)
                .order_by(ToolRegistry.name.asc())
            )
        ).all()
        credential_id_str = str(credential_id)
        tools: list[dict[str, Any]] = []
        for tool_id, tool_name, builtin_key, implementation_type, config_schema in tool_rows:
            impl = (config_schema or {}).get("implementation") if isinstance(config_schema, dict) else {}
            if str((impl or {}).get("credentials_ref") or "") != credential_id_str:
                continue
            tools.append(
                {
                    "tool_id": tool_id,
                    "tool_name": tool_name,
                    "builtin_key": builtin_key,
                    "implementation_type": str(getattr(implementation_type, "value", implementation_type)) if implementation_type else None,
                }
            )
        return {
            "credential_id": credential_id,
            "model_providers": [
                {
                    "binding_id": row[0],
                    "model_id": row[1],
                    "model_name": row[2],
                    "provider": str(getattr(row[3], "value", row[3])),
                    "provider_model_id": row[4],
                }
                for row in model_rows
            ],
            "knowledge_stores": [
                {
                    "store_id": row[0],
                    "store_name": row[1],
                    "backend": str(getattr(row[2], "value", row[2])),
                }
                for row in store_rows
            ],
            "tools": tools,
        }

    async def delete_credential(self, *, ctx: ControlPlaneContext, credential_id: UUID, force_disconnect: bool) -> None:
        stmt = select(IntegrationCredential).where(
            and_(IntegrationCredential.id == credential_id, IntegrationCredential.organization_id == ctx.organization_id)
        )
        credential = (await self.db.execute(stmt)).scalar_one_or_none()
        if credential is None:
            raise not_found("Credential not found")
        usage = await self.get_usage(ctx=ctx, credential_id=credential_id)
        total_links = len(usage["model_providers"]) + len(usage["knowledge_stores"]) + len(usage["tools"])
        if total_links and not force_disconnect:
            raise validation(
                "Credential is in use",
                usage=usage,
                hint="Re-run delete with force_disconnect=true to detach linked resources and use platform defaults.",
            )
        if total_links and force_disconnect:
            await self.db.execute(
                update(ModelProviderBinding)
                .where(
                    ModelProviderBinding.organization_id == ctx.organization_id,
                    ModelProviderBinding.credentials_ref == credential_id,
                )
                .values(credentials_ref=None)
            )
            await self.db.execute(
                update(KnowledgeStore)
                .where(KnowledgeStore.organization_id == ctx.organization_id, KnowledgeStore.credentials_ref == credential_id)
                .values(credentials_ref=None)
            )
            tools = (
                await self.db.execute(select(ToolRegistry).where(ToolRegistry.organization_id == ctx.organization_id))
            ).scalars().all()
            for tool in tools:
                config_schema = dict(tool.config_schema or {})
                implementation = dict(config_schema.get("implementation") or {})
                if str(implementation.get("credentials_ref") or "") != str(credential_id):
                    continue
                implementation.pop("credentials_ref", None)
                config_schema["implementation"] = implementation
                tool.config_schema = config_schema
        await self.db.delete(credential)
        await self.db.commit()
