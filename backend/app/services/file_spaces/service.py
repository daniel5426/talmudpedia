from __future__ import annotations

import base64
import hashlib
import mimetypes
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.agents import Agent
from app.db.postgres.models.files import (
    AgentFileSpaceLink,
    FileAccessMode,
    FileEntryRevision,
    FileEntryType,
    FileSpace,
    FileSpaceEntry,
    FileSpaceStatus,
)
from app.db.postgres.models.workspace import Project
from app.services.file_spaces.storage import FileSpaceStorage


TEXT_MIME_FALLBACKS = {
    ".md": "text/markdown",
    ".txt": "text/plain",
    ".json": "application/json",
    ".js": "application/javascript",
    ".ts": "application/typescript",
    ".tsx": "text/tsx",
    ".jsx": "text/jsx",
    ".py": "text/x-python",
    ".html": "text/html",
    ".css": "text/css",
    ".csv": "text/csv",
    ".yml": "application/yaml",
    ".yaml": "application/yaml",
    ".xml": "application/xml",
    ".sql": "application/sql",
}


class FileSpaceServiceError(Exception):
    pass


class FileSpaceNotFoundError(FileSpaceServiceError):
    pass


class FileSpaceValidationError(FileSpaceServiceError):
    pass


class FileSpacePermissionError(FileSpaceServiceError):
    pass


@dataclass(frozen=True)
class FileSpaceGrant:
    id: UUID
    name: str
    access_mode: FileAccessMode

    def to_runtime_payload(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "name": self.name,
            "access_mode": getattr(self.access_mode, "value", self.access_mode),
        }


class FileSpaceService:
    def __init__(self, db: AsyncSession, *, storage: FileSpaceStorage | None = None):
        self.db = db
        self.storage = storage or FileSpaceStorage()

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _normalize_name(name: str) -> str:
        normalized = str(name or "").strip()
        if not normalized:
            raise FileSpaceValidationError("name is required")
        return normalized

    @classmethod
    def normalize_path(cls, path: str) -> str:
        raw = str(path or "").replace("\\", "/").strip()
        if not raw:
            raise FileSpaceValidationError("path is required")
        if raw.startswith("/"):
            raise FileSpaceValidationError("absolute paths are not allowed")
        parts: list[str] = []
        for part in raw.split("/"):
            if not part or part == ".":
                continue
            if part == "..":
                raise FileSpaceValidationError("path traversal is not allowed")
            parts.append(part)
        normalized = "/".join(parts)
        if not normalized:
            raise FileSpaceValidationError("path is required")
        return normalized

    @classmethod
    def _normalize_file_path(cls, path: str) -> str:
        normalized = cls.normalize_path(path)
        if normalized.endswith("/"):
            raise FileSpaceValidationError("file path must not end with '/'")
        return normalized

    @classmethod
    def _normalize_directory_path(cls, path: str) -> str:
        normalized = cls.normalize_path(path)
        if normalized == "":
            raise FileSpaceValidationError("directory path is required")
        return normalized

    @staticmethod
    def _parent_paths(path: str) -> list[str]:
        parts = PurePosixPath(path).parts[:-1]
        parents: list[str] = []
        running: list[str] = []
        for part in parts:
            running.append(part)
            parents.append("/".join(running))
        return parents

    @staticmethod
    def _parent_directory(path: str) -> str | None:
        parent = PurePosixPath(path).parent.as_posix()
        if parent in {"", "."}:
            return None
        return parent

    @staticmethod
    def _is_text_mime(mime_type: str) -> bool:
        normalized = str(mime_type or "").strip().lower()
        return normalized.startswith("text/") or normalized in {
            "application/json",
            "application/javascript",
            "application/typescript",
            "application/xml",
            "application/yaml",
            "application/sql",
        }

    @classmethod
    def _resolve_mime_type(cls, *, filename: str | None, explicit: str | None, payload: bytes | None = None) -> tuple[str, bool]:
        normalized = str(explicit or "").split(";", 1)[0].strip().lower()
        suffix = PurePosixPath(filename or "").suffix.lower()
        guessed = TEXT_MIME_FALLBACKS.get(suffix)
        if not normalized:
            normalized = guessed or mimetypes.guess_type(filename or "")[0] or "application/octet-stream"
        is_text = cls._is_text_mime(normalized)
        if not explicit and not is_text and payload is not None:
            try:
                payload.decode("utf-8")
                is_text = True
            except Exception:
                is_text = False
        return normalized, is_text

    @staticmethod
    def _sha256(payload: bytes) -> str:
        return hashlib.sha256(payload).hexdigest()

    async def _require_project(self, *, organization_id: UUID, project_id: UUID) -> Project:
        project = await self.db.scalar(
            select(Project).where(Project.id == project_id, Project.organization_id == organization_id)
        )
        if project is None:
            raise FileSpaceNotFoundError("project not found")
        return project

    async def list_spaces(self, *, organization_id: UUID, project_id: UUID) -> list[tuple[FileSpace, int, int]]:
        await self._require_project(organization_id=organization_id, project_id=project_id)
        result = await self.db.execute(
            select(
                FileSpace,
                func.count(FileSpaceEntry.id).label("file_count"),
                func.coalesce(func.sum(FileSpaceEntry.byte_size), 0).label("total_bytes"),
            )
            .outerjoin(
                FileSpaceEntry,
                and_(
                    FileSpaceEntry.space_id == FileSpace.id,
                    FileSpaceEntry.deleted_at.is_(None),
                    FileSpaceEntry.entry_type == FileEntryType.file,
                ),
            )
            .where(
                FileSpace.organization_id == organization_id,
                FileSpace.project_id == project_id,
                FileSpace.status != FileSpaceStatus.archived,
            )
            .group_by(FileSpace.id)
            .order_by(FileSpace.updated_at.desc(), FileSpace.created_at.desc())
        )
        return [(space, int(file_count or 0), int(total_bytes or 0)) for space, file_count, total_bytes in result.all()]

    async def create_space(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        name: str,
        description: str | None,
        created_by: UUID | None,
    ) -> FileSpace:
        await self._require_project(organization_id=organization_id, project_id=project_id)
        space = FileSpace(
            organization_id=organization_id,
            project_id=project_id,
            name=self._normalize_name(name),
            description=str(description or "").strip() or None,
            status=FileSpaceStatus.active,
            created_by=created_by,
        )
        self.db.add(space)
        await self.db.flush()
        return space

    async def get_space(self, *, organization_id: UUID, project_id: UUID, space_id: UUID) -> FileSpace:
        space = await self.db.scalar(
            select(FileSpace).where(
                FileSpace.id == space_id,
                FileSpace.organization_id == organization_id,
                FileSpace.project_id == project_id,
            )
        )
        if space is None or space.status == FileSpaceStatus.archived:
            raise FileSpaceNotFoundError("file space not found")
        return space

    async def archive_space(self, *, organization_id: UUID, project_id: UUID, space_id: UUID) -> FileSpace:
        space = await self.get_space(organization_id=organization_id, project_id=project_id, space_id=space_id)
        space.status = FileSpaceStatus.archived
        return space

    async def list_entries(self, *, organization_id: UUID, project_id: UUID, space_id: UUID) -> list[FileSpaceEntry]:
        await self.get_space(organization_id=organization_id, project_id=project_id, space_id=space_id)
        result = await self.db.execute(
            select(FileSpaceEntry)
            .where(
                FileSpaceEntry.space_id == space_id,
                FileSpaceEntry.deleted_at.is_(None),
            )
            .order_by(FileSpaceEntry.path.asc())
        )
        return list(result.scalars().all())

    async def _get_entry(self, *, space_id: UUID, path: str, include_deleted: bool = False) -> FileSpaceEntry | None:
        stmt = select(FileSpaceEntry).where(
            FileSpaceEntry.space_id == space_id,
            FileSpaceEntry.path == path,
        )
        if not include_deleted:
            stmt = stmt.where(FileSpaceEntry.deleted_at.is_(None))
        return await self.db.scalar(stmt)

    async def _get_directory_children(self, *, space_id: UUID, path: str) -> list[FileSpaceEntry]:
        prefix = f"{path}/"
        result = await self.db.execute(
            select(FileSpaceEntry).where(
                FileSpaceEntry.space_id == space_id,
                FileSpaceEntry.deleted_at.is_(None),
                or_(FileSpaceEntry.path == path, FileSpaceEntry.path.startswith(prefix)),
            )
        )
        return list(result.scalars().all())

    async def _ensure_directory_chain(self, *, space: FileSpace, path: str, user_id: UUID | None) -> None:
        for parent in self._parent_paths(path):
            entry = await self._get_entry(space_id=space.id, path=parent, include_deleted=True)
            if entry is None:
                self.db.add(
                    FileSpaceEntry(
                        id=uuid4(),
                        space_id=space.id,
                        path=parent,
                        entry_type=FileEntryType.directory,
                        created_by=user_id,
                        updated_by=user_id,
                        deleted_at=None,
                    )
                )
                continue
            if entry.entry_type != FileEntryType.directory:
                raise FileSpaceValidationError(f"parent path '{parent}' is not a directory")
            entry.deleted_at = None
            entry.updated_by = user_id

    async def mkdir(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        space_id: UUID,
        path: str,
        user_id: UUID | None,
    ) -> FileSpaceEntry:
        space = await self.get_space(organization_id=organization_id, project_id=project_id, space_id=space_id)
        normalized = self._normalize_directory_path(path)
        await self._ensure_directory_chain(space=space, path=normalized, user_id=user_id)
        existing = await self._get_entry(space_id=space.id, path=normalized, include_deleted=True)
        if existing is None:
            existing = FileSpaceEntry(
                id=uuid4(),
                space_id=space.id,
                path=normalized,
                entry_type=FileEntryType.directory,
                created_by=user_id,
                updated_by=user_id,
            )
            self.db.add(existing)
        elif existing.entry_type != FileEntryType.directory:
            raise FileSpaceValidationError(f"path '{normalized}' already exists as a file")
        else:
            existing.deleted_at = None
            existing.updated_by = user_id
        await self.db.flush()
        return existing

    async def _upsert_file_revision(
        self,
        *,
        space: FileSpace,
        path: str,
        payload: bytes,
        mime_type: str,
        is_text: bool,
        encoding: str | None,
        user_id: UUID | None,
        run_id: UUID | None,
    ) -> tuple[FileSpaceEntry, FileEntryRevision]:
        await self._ensure_directory_chain(space=space, path=path, user_id=user_id)
        entry = await self._get_entry(space_id=space.id, path=path, include_deleted=True)
        if entry is None:
            entry = FileSpaceEntry(
                id=uuid4(),
                space_id=space.id,
                path=path,
                entry_type=FileEntryType.file,
                created_by=user_id,
                updated_by=user_id,
                deleted_at=None,
            )
            self.db.add(entry)
            await self.db.flush()
        elif entry.entry_type != FileEntryType.file:
            raise FileSpaceValidationError(f"path '{path}' already exists as a directory")
        else:
            entry.deleted_at = None
            entry.updated_by = user_id

        filename = PurePosixPath(path).name or "file.bin"
        revision_id = uuid4()
        storage_key = self.storage.write_bytes(
            project_id=str(space.project_id),
            space_id=str(space.id),
            entry_id=str(entry.id),
            revision_id=str(revision_id),
            filename=filename,
            payload=payload,
            content_type=mime_type,
        )
        revision = FileEntryRevision(
            id=revision_id,
            entry_id=entry.id,
            storage_key=storage_key,
            mime_type=mime_type,
            byte_size=len(payload),
            sha256=self._sha256(payload),
            is_text=is_text,
            encoding=encoding,
            created_by=user_id,
            created_by_run_id=run_id,
        )
        self.db.add(revision)
        await self.db.flush()

        entry.current_revision_id = revision.id
        entry.mime_type = revision.mime_type
        entry.byte_size = revision.byte_size
        entry.sha256 = revision.sha256
        entry.is_text = revision.is_text
        entry.updated_by = user_id
        await self.db.flush()
        return entry, revision

    async def write_text_file(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        space_id: UUID,
        path: str,
        content: str,
        user_id: UUID | None,
        run_id: UUID | None = None,
        mime_type: str | None = None,
    ) -> tuple[FileSpaceEntry, FileEntryRevision]:
        space = await self.get_space(organization_id=organization_id, project_id=project_id, space_id=space_id)
        normalized = self._normalize_file_path(path)
        payload = str(content or "").encode("utf-8")
        resolved_mime, _ = self._resolve_mime_type(filename=normalized, explicit=mime_type, payload=payload)
        return await self._upsert_file_revision(
            space=space,
            path=normalized,
            payload=payload,
            mime_type=resolved_mime,
            is_text=True,
            encoding="utf-8",
            user_id=user_id,
            run_id=run_id,
        )

    async def upload_file(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        space_id: UUID,
        path: str,
        payload: bytes,
        content_type: str | None,
        user_id: UUID | None,
        run_id: UUID | None = None,
    ) -> tuple[FileSpaceEntry, FileEntryRevision]:
        space = await self.get_space(organization_id=organization_id, project_id=project_id, space_id=space_id)
        normalized = self._normalize_file_path(path)
        mime_type, is_text = self._resolve_mime_type(filename=normalized, explicit=content_type, payload=payload)
        encoding = None
        if is_text:
            try:
                payload.decode("utf-8")
                encoding = "utf-8"
            except Exception:
                is_text = False
        return await self._upsert_file_revision(
            space=space,
            path=normalized,
            payload=payload,
            mime_type=mime_type,
            is_text=is_text,
            encoding=encoding,
            user_id=user_id,
            run_id=run_id,
        )

    async def read_entry(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        space_id: UUID,
        path: str,
    ) -> tuple[FileSpaceEntry, FileEntryRevision | None]:
        await self.get_space(organization_id=organization_id, project_id=project_id, space_id=space_id)
        normalized = self.normalize_path(path)
        entry = await self._get_entry(space_id=space_id, path=normalized)
        if entry is None:
            raise FileSpaceNotFoundError("entry not found")
        revision = None
        if entry.current_revision_id:
            revision = await self.db.get(FileEntryRevision, entry.current_revision_id)
        return entry, revision

    async def read_text_file(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        space_id: UUID,
        path: str,
    ) -> tuple[FileSpaceEntry, FileEntryRevision, str]:
        entry, revision = await self.read_entry(
            organization_id=organization_id,
            project_id=project_id,
            space_id=space_id,
            path=path,
        )
        if entry.entry_type != FileEntryType.file or revision is None:
            raise FileSpaceValidationError("entry is not a readable file")
        if not revision.is_text:
            raise FileSpaceValidationError("file is binary and cannot be read as text")
        payload = self.storage.read_bytes(storage_key=revision.storage_key)
        return entry, revision, payload.decode(revision.encoding or "utf-8", errors="replace")

    async def read_file_bytes(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        space_id: UUID,
        path: str,
    ) -> tuple[FileSpaceEntry, FileEntryRevision, bytes]:
        entry, revision = await self.read_entry(
            organization_id=organization_id,
            project_id=project_id,
            space_id=space_id,
            path=path,
        )
        if entry.entry_type != FileEntryType.file or revision is None:
            raise FileSpaceValidationError("entry is not a file")
        return entry, revision, self.storage.read_bytes(storage_key=revision.storage_key)

    async def patch_text_file(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        space_id: UUID,
        path: str,
        old_text: str,
        new_text: str,
        user_id: UUID | None,
        run_id: UUID | None = None,
    ) -> tuple[FileSpaceEntry, FileEntryRevision]:
        entry, _revision, content = await self.read_text_file(
            organization_id=organization_id,
            project_id=project_id,
            space_id=space_id,
            path=path,
        )
        if old_text not in content:
            raise FileSpaceValidationError("old_text was not found in file")
        updated = content.replace(old_text, new_text, 1)
        return await self.write_text_file(
            organization_id=organization_id,
            project_id=project_id,
            space_id=space_id,
            path=entry.path,
            content=updated,
            user_id=user_id,
            run_id=run_id,
            mime_type=entry.mime_type,
        )

    async def move_entry(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        space_id: UUID,
        from_path: str,
        to_path: str,
        user_id: UUID | None,
    ) -> list[FileSpaceEntry]:
        space = await self.get_space(organization_id=organization_id, project_id=project_id, space_id=space_id)
        source = self.normalize_path(from_path)
        target = self.normalize_path(to_path)
        entry = await self._get_entry(space_id=space.id, path=source)
        if entry is None:
            raise FileSpaceNotFoundError("source entry not found")
        if source == target:
            return [entry]
        if entry.entry_type == FileEntryType.directory and target.startswith(f"{source}/"):
            raise FileSpaceValidationError("directory cannot be moved into itself")

        target_parent = self._parent_directory(target)
        if target_parent:
            await self._ensure_directory_chain(space=space, path=f"{target_parent}/placeholder", user_id=user_id)

        source_children = await self._get_directory_children(space_id=space.id, path=source)
        if entry.entry_type == FileEntryType.file:
            source_children = [entry]
        renamed: list[FileSpaceEntry] = []
        prefix = f"{source}/"
        for child in source_children:
            suffix = child.path[len(prefix):] if child.path.startswith(prefix) else ""
            next_path = target if child.path == source else f"{target}/{suffix}"
            existing = await self._get_entry(space_id=space.id, path=next_path)
            if existing is not None and existing.id != child.id:
                raise FileSpaceValidationError(f"destination path '{next_path}' already exists")
        for child in source_children:
            suffix = child.path[len(prefix):] if child.path.startswith(prefix) else ""
            child.path = target if child.path == source else f"{target}/{suffix}"
            child.updated_by = user_id
            renamed.append(child)
        await self.db.flush()
        return renamed

    async def delete_entry(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        space_id: UUID,
        path: str,
        user_id: UUID | None,
    ) -> list[FileSpaceEntry]:
        await self.get_space(organization_id=organization_id, project_id=project_id, space_id=space_id)
        normalized = self.normalize_path(path)
        entry = await self._get_entry(space_id=space_id, path=normalized)
        if entry is None:
            raise FileSpaceNotFoundError("entry not found")
        targets = [entry] if entry.entry_type == FileEntryType.file else await self._get_directory_children(space_id=space_id, path=normalized)
        deleted_at = self._utcnow()
        for item in targets:
            item.deleted_at = deleted_at
            item.updated_by = user_id
        await self.db.flush()
        return targets

    async def list_revisions(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        space_id: UUID,
        path: str,
    ) -> list[FileEntryRevision]:
        entry, _ = await self.read_entry(
            organization_id=organization_id,
            project_id=project_id,
            space_id=space_id,
            path=path,
        )
        if entry.entry_type != FileEntryType.file:
            return []
        result = await self.db.execute(
            select(FileEntryRevision)
            .where(FileEntryRevision.entry_id == entry.id)
            .order_by(FileEntryRevision.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_agent_links(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        space_id: UUID,
    ) -> list[AgentFileSpaceLink]:
        await self.get_space(organization_id=organization_id, project_id=project_id, space_id=space_id)
        result = await self.db.execute(
            select(AgentFileSpaceLink)
            .where(
                AgentFileSpaceLink.organization_id == organization_id,
                AgentFileSpaceLink.project_id == project_id,
                AgentFileSpaceLink.file_space_id == space_id,
            )
            .order_by(AgentFileSpaceLink.created_at.asc())
        )
        return list(result.scalars().all())

    async def upsert_agent_link(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        agent_id: UUID,
        space_id: UUID,
        access_mode: FileAccessMode,
        user_id: UUID | None,
    ) -> AgentFileSpaceLink:
        await self.get_space(organization_id=organization_id, project_id=project_id, space_id=space_id)
        agent = await self.db.scalar(select(Agent).where(Agent.id == agent_id, Agent.organization_id == organization_id))
        if agent is None:
            raise FileSpaceNotFoundError("agent not found")
        link = await self.db.scalar(
            select(AgentFileSpaceLink).where(
                AgentFileSpaceLink.project_id == project_id,
                AgentFileSpaceLink.agent_id == agent_id,
                AgentFileSpaceLink.file_space_id == space_id,
            )
        )
        if link is None:
            link = AgentFileSpaceLink(
                organization_id=organization_id,
                project_id=project_id,
                agent_id=agent_id,
                file_space_id=space_id,
                access_mode=access_mode,
                created_by=user_id,
            )
            self.db.add(link)
        else:
            link.access_mode = access_mode
        await self.db.flush()
        return link

    async def delete_agent_link(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        agent_id: UUID,
        space_id: UUID,
    ) -> None:
        link = await self.db.scalar(
            select(AgentFileSpaceLink).where(
                AgentFileSpaceLink.organization_id == organization_id,
                AgentFileSpaceLink.project_id == project_id,
                AgentFileSpaceLink.agent_id == agent_id,
                AgentFileSpaceLink.file_space_id == space_id,
            )
        )
        if link is None:
            return
        await self.db.delete(link)
        await self.db.flush()

    async def resolve_agent_file_space_grants(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        agent_id: UUID,
    ) -> list[FileSpaceGrant]:
        if project_id is None:
            return []
        result = await self.db.execute(
            select(AgentFileSpaceLink, FileSpace)
            .join(FileSpace, FileSpace.id == AgentFileSpaceLink.file_space_id)
            .where(
                AgentFileSpaceLink.organization_id == organization_id,
                AgentFileSpaceLink.project_id == project_id,
                AgentFileSpaceLink.agent_id == agent_id,
                FileSpace.status == FileSpaceStatus.active,
            )
            .order_by(FileSpace.name.asc(), FileSpace.created_at.asc())
        )
        grants: list[FileSpaceGrant] = []
        for link, space in result.all():
            grants.append(
                FileSpaceGrant(
                    id=space.id,
                    name=space.name,
                    access_mode=FileAccessMode(str(getattr(link.access_mode, "value", link.access_mode))),
                )
            )
        return grants

    @staticmethod
    def serialize_space(
        space: FileSpace,
        *,
        view: str = "full",
        file_count: int | None = None,
        total_bytes: int | None = None,
    ) -> dict[str, Any]:
        payload = {
            "id": str(space.id),
            "organization_id": str(space.organization_id),
            "project_id": str(space.project_id),
            "name": space.name,
            "status": getattr(space.status, "value", space.status),
            "file_count": int(file_count) if file_count is not None else None,
            "total_bytes": int(total_bytes) if total_bytes is not None else None,
            "created_at": space.created_at.isoformat() if space.created_at else None,
            "updated_at": space.updated_at.isoformat() if space.updated_at else None,
        }
        if view == "summary":
            return payload
        payload["description"] = space.description
        return payload

    @staticmethod
    def serialize_entry(entry: FileSpaceEntry) -> dict[str, Any]:
        return {
            "id": str(entry.id),
            "space_id": str(entry.space_id),
            "path": entry.path,
            "name": PurePosixPath(entry.path).name or entry.path,
            "parent_path": str(PurePosixPath(entry.path).parent).replace(".", "") or None,
            "entry_type": getattr(entry.entry_type, "value", entry.entry_type),
            "current_revision_id": str(entry.current_revision_id) if entry.current_revision_id else None,
            "mime_type": entry.mime_type,
            "byte_size": int(entry.byte_size or 0) if entry.byte_size is not None else None,
            "sha256": entry.sha256,
            "is_text": bool(entry.is_text),
            "deleted_at": entry.deleted_at.isoformat() if entry.deleted_at else None,
            "created_at": entry.created_at.isoformat() if entry.created_at else None,
            "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
        }

    @staticmethod
    def serialize_revision(revision: FileEntryRevision) -> dict[str, Any]:
        return {
            "id": str(revision.id),
            "entry_id": str(revision.entry_id),
            "storage_key": revision.storage_key,
            "mime_type": revision.mime_type,
            "byte_size": int(revision.byte_size or 0),
            "sha256": revision.sha256,
            "is_text": bool(revision.is_text),
            "encoding": revision.encoding,
            "created_by": str(revision.created_by) if revision.created_by else None,
            "created_by_run_id": str(revision.created_by_run_id) if revision.created_by_run_id else None,
            "created_at": revision.created_at.isoformat() if revision.created_at else None,
        }

    @staticmethod
    def serialize_link(link: AgentFileSpaceLink) -> dict[str, Any]:
        return {
            "id": str(link.id),
            "organization_id": str(link.organization_id),
            "project_id": str(link.project_id),
            "agent_id": str(link.agent_id),
            "file_space_id": str(link.file_space_id),
            "access_mode": getattr(link.access_mode, "value", link.access_mode),
            "created_by": str(link.created_by) if link.created_by else None,
            "created_at": link.created_at.isoformat() if link.created_at else None,
            "updated_at": link.updated_at.isoformat() if link.updated_at else None,
        }

    @staticmethod
    def serialize_text_read(entry: FileSpaceEntry, revision: FileEntryRevision, content: str) -> dict[str, Any]:
        return {
            "entry": FileSpaceService.serialize_entry(entry),
            "revision": FileSpaceService.serialize_revision(revision),
            "content": content,
        }

    @staticmethod
    def serialize_binary_read(entry: FileSpaceEntry, revision: FileEntryRevision, payload: bytes) -> dict[str, Any]:
        return {
            "entry": FileSpaceService.serialize_entry(entry),
            "revision": FileSpaceService.serialize_revision(revision),
            "content_base64": base64.b64encode(payload).decode("ascii"),
        }
