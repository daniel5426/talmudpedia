from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scope_registry import is_platform_admin_role
from app.db.postgres.models.prompts import (
    PromptLibrary,
    PromptLibraryVersion,
    PromptOwnership,
    PromptScope,
    PromptStatus,
)

from .prompt_reference_resolver import PromptReferenceResolver


class PromptLibraryError(ValueError):
    pass


class PromptAccessError(PromptLibraryError):
    pass


class PromptUsageError(PromptLibraryError):
    pass


@dataclass
class PromptCreateData:
    name: str
    description: str | None
    content: str
    scope: PromptScope = PromptScope.TENANT
    allowed_surfaces: list[str] | None = None
    tags: list[str] | None = None


@dataclass
class PromptUpdateData:
    name: str | None = None
    description: str | None = None
    content: str | None = None
    allowed_surfaces: list[str] | None = None
    tags: list[str] | None = None


class PromptLibraryService:
    def __init__(
        self,
        db: AsyncSession,
        *,
        tenant_id: UUID | None,
        actor_user_id: UUID | None = None,
        actor_role: str | None = None,
        is_service: bool = False,
    ):
        self._db = db
        self._tenant_id = tenant_id
        self._actor_user_id = actor_user_id
        self._actor_role = actor_role
        self._is_service = is_service

    @property
    def resolver(self) -> PromptReferenceResolver:
        return PromptReferenceResolver(self._db, self._tenant_id)

    def _can_manage_global(self) -> bool:
        if self._is_service:
            return True
        return is_platform_admin_role(self._actor_role)

    def _scope_tenant_id(self, scope: PromptScope) -> UUID | None:
        scope_value = getattr(scope, "value", scope)
        if str(scope_value or "").strip().lower() == PromptScope.GLOBAL.value:
            if not self._can_manage_global():
                raise PromptAccessError("Global prompts require platform admin privileges")
            return None
        if self._tenant_id is None:
            raise PromptAccessError("Tenant context required for tenant prompts")
        return self._tenant_id

    @staticmethod
    def _normalize_string_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        result: list[str] = []
        for item in value:
            text = str(item or "").strip()
            if text:
                result.append(text)
        return result

    async def _record_version(self, prompt: PromptLibrary) -> PromptLibraryVersion:
        version_row = PromptLibraryVersion(
            prompt_id=prompt.id,
            version=int(prompt.version or 1),
            name=str(prompt.name or ""),
            description=prompt.description,
            content=str(prompt.content or ""),
            allowed_surfaces=self._normalize_string_list(prompt.allowed_surfaces),
            tags=self._normalize_string_list(prompt.tags),
            created_by=self._actor_user_id,
        )
        self._db.add(version_row)
        await self._db.flush()
        return version_row

    async def list_prompts(
        self,
        *,
        q: str | None = None,
        status: PromptStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[PromptLibrary], int]:
        conditions = [or_(PromptLibrary.tenant_id == self._tenant_id, PromptLibrary.tenant_id.is_(None))]
        if status is not None:
            conditions.append(PromptLibrary.status == getattr(status, "value", status))
        if q:
            pattern = f"%{str(q).strip().lower()}%"
            conditions.append(
                or_(
                    func.lower(PromptLibrary.name).like(pattern),
                    func.lower(func.coalesce(PromptLibrary.description, "")).like(pattern),
                )
            )
        stmt = (
            select(PromptLibrary)
            .where(and_(*conditions))
            .order_by(PromptLibrary.updated_at.desc(), PromptLibrary.name.asc())
            .offset(max(offset, 0))
            .limit(max(1, min(limit, 500)))
        )
        prompts = list((await self._db.execute(stmt)).scalars().all())
        count_stmt = select(func.count(PromptLibrary.id)).where(and_(*conditions))
        total = int((await self._db.execute(count_stmt)).scalar_one() or 0)
        return prompts, total

    async def search_mentions(
        self,
        *,
        q: str | None,
        surface: str | None,
        limit: int = 25,
    ) -> list[PromptLibrary]:
        conditions = [
            or_(PromptLibrary.tenant_id == self._tenant_id, PromptLibrary.tenant_id.is_(None)),
            PromptLibrary.status == PromptStatus.ACTIVE.value,
        ]
        if q:
            pattern = f"%{str(q).strip().lower()}%"
            conditions.append(
                or_(
                    func.lower(PromptLibrary.name).like(pattern),
                    func.lower(func.coalesce(PromptLibrary.description, "")).like(pattern),
                )
            )
        stmt = (
            select(PromptLibrary)
            .where(and_(*conditions))
            .order_by(PromptLibrary.name.asc(), PromptLibrary.updated_at.desc())
            .limit(max(1, min(limit, 100)))
        )
        rows = list((await self._db.execute(stmt)).scalars().all())
        if not surface:
            return rows
        visible: list[PromptLibrary] = []
        for prompt in rows:
            allowed_surfaces = self._normalize_string_list(prompt.allowed_surfaces)
            if not allowed_surfaces or surface in allowed_surfaces:
                visible.append(prompt)
        return visible

    async def get_prompt(self, prompt_id: UUID) -> PromptLibrary:
        stmt = select(PromptLibrary).where(
            PromptLibrary.id == prompt_id,
            or_(PromptLibrary.tenant_id == self._tenant_id, PromptLibrary.tenant_id.is_(None)),
        )
        prompt = (await self._db.execute(stmt)).scalar_one_or_none()
        if prompt is None:
            raise PromptAccessError("Prompt not found")
        return prompt

    async def create_prompt(self, data: PromptCreateData) -> PromptLibrary:
        tenant_id = self._scope_tenant_id(data.scope)
        prompt = PromptLibrary(
            tenant_id=tenant_id,
            name=str(data.name or "").strip(),
            description=data.description,
            content=str(data.content or ""),
            scope=getattr(data.scope, "value", data.scope),
            status=PromptStatus.ACTIVE.value,
            ownership=PromptOwnership.MANUAL.value,
            managed_by="prompts",
            allowed_surfaces=self._normalize_string_list(data.allowed_surfaces),
            tags=self._normalize_string_list(data.tags),
            version=1,
        )
        if not prompt.name:
            raise PromptLibraryError("Prompt name is required")
        await PromptReferenceResolver(self._db, tenant_id).validate_text(
            prompt.content,
            surface=None,
            current_prompt_id=prompt.id,
        )
        self._db.add(prompt)
        await self._db.flush()
        await self._record_version(prompt)
        return prompt

    async def update_prompt(self, prompt_id: UUID, data: PromptUpdateData) -> PromptLibrary:
        prompt = await self.get_prompt(prompt_id)
        ownership = getattr(getattr(prompt, "ownership", None), "value", getattr(prompt, "ownership", None))
        if str(ownership or "").strip().lower() == PromptOwnership.SYSTEM.value and not self._can_manage_global():
            raise PromptAccessError("System prompts are read-only")

        changed = False
        if data.name is not None:
            name = str(data.name or "").strip()
            if not name:
                raise PromptLibraryError("Prompt name cannot be empty")
            if name != prompt.name:
                prompt.name = name
                changed = True
        if data.description is not None and data.description != prompt.description:
            prompt.description = data.description
            changed = True
        if data.content is not None and data.content != prompt.content:
            prompt.content = str(data.content or "")
            changed = True
        if data.allowed_surfaces is not None:
            normalized = self._normalize_string_list(data.allowed_surfaces)
            if normalized != self._normalize_string_list(prompt.allowed_surfaces):
                prompt.allowed_surfaces = normalized
                changed = True
        if data.tags is not None:
            normalized = self._normalize_string_list(data.tags)
            if normalized != self._normalize_string_list(prompt.tags):
                prompt.tags = normalized
                changed = True
        if not changed:
            return prompt

        await PromptReferenceResolver(self._db, prompt.tenant_id).validate_text(
            prompt.content,
            surface=None,
            current_prompt_id=prompt.id,
        )
        prompt.version = int(prompt.version or 1) + 1
        await self._db.flush()
        await self._record_version(prompt)
        return prompt

    async def archive_prompt(self, prompt_id: UUID) -> PromptLibrary:
        prompt = await self.get_prompt(prompt_id)
        prompt.status = PromptStatus.ARCHIVED.value
        await self._db.flush()
        return prompt

    async def restore_prompt(self, prompt_id: UUID) -> PromptLibrary:
        prompt = await self.get_prompt(prompt_id)
        prompt.status = PromptStatus.ACTIVE.value
        await self._db.flush()
        return prompt

    async def delete_prompt(self, prompt_id: UUID) -> None:
        prompt = await self.get_prompt(prompt_id)
        usage = await self.resolver.scan_usage(prompt_id=prompt.id)
        if usage:
            raise PromptUsageError("Prompt is still referenced and cannot be deleted")
        await self._db.delete(prompt)
        await self._db.flush()

    async def list_versions(self, prompt_id: UUID) -> list[PromptLibraryVersion]:
        prompt = await self.get_prompt(prompt_id)
        stmt = (
            select(PromptLibraryVersion)
            .where(PromptLibraryVersion.prompt_id == prompt.id)
            .order_by(PromptLibraryVersion.version.desc(), PromptLibraryVersion.created_at.desc())
        )
        return list((await self._db.execute(stmt)).scalars().all())

    async def rollback(self, prompt_id: UUID, *, version: int) -> PromptLibrary:
        prompt = await self.get_prompt(prompt_id)
        snapshot = (
            await self._db.execute(
                select(PromptLibraryVersion).where(
                    PromptLibraryVersion.prompt_id == prompt.id,
                    PromptLibraryVersion.version == int(version),
                )
            )
        ).scalar_one_or_none()
        if snapshot is None:
            raise PromptLibraryError(f"Prompt version {version} was not found")

        prompt.name = snapshot.name
        prompt.description = snapshot.description
        prompt.content = snapshot.content
        prompt.allowed_surfaces = self._normalize_string_list(snapshot.allowed_surfaces)
        prompt.tags = self._normalize_string_list(snapshot.tags)
        prompt.version = int(prompt.version or 1) + 1
        await PromptReferenceResolver(self._db, prompt.tenant_id).validate_text(
            prompt.content,
            surface=None,
            current_prompt_id=prompt.id,
        )
        await self._db.flush()
        await self._record_version(prompt)
        return prompt

    async def usage(self, prompt_id: UUID) -> list[dict[str, Any]]:
        prompt = await self.get_prompt(prompt_id)
        return await self.resolver.scan_usage(prompt_id=prompt.id)
