from __future__ import annotations

import json
import os
from hashlib import sha256
from typing import Dict

from sqlalchemy import insert
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.published_apps import PublishedAppRevision, PublishedAppRevisionBlob
from app.services.published_app_bundle_storage import (
    PublishedAppBundleStorage,
    PublishedAppBundleStorageNotConfigured,
)


REVISION_BLOB_PREFIX = "apps/revision-blobs"


class PublishedAppRevisionStore:
    def __init__(self, db: AsyncSession):
        self._db = db
        if os.getenv("PYTEST_CURRENT_TEST"):
            # Test runs should stay fully local and deterministic.
            self._storage = None
            return
        try:
            self._storage = PublishedAppBundleStorage.from_env()
        except PublishedAppBundleStorageNotConfigured:
            self._storage = None

    @staticmethod
    def _hash_content(content: str) -> str:
        return sha256(str(content or "").encode("utf-8")).hexdigest()

    @staticmethod
    def _manifest_bundle_hash(manifest: Dict[str, str]) -> str:
        payload = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
        return sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _blob_asset_path(blob_hash: str) -> str:
        return f"sha256/{blob_hash}"

    async def build_manifest_and_store_blobs(self, files: Dict[str, str]) -> tuple[Dict[str, str], str]:
        normalized_files: Dict[str, str] = {
            str(path): str(content if isinstance(content, str) else str(content))
            for path, content in (files or {}).items()
            if isinstance(path, str) and str(path).strip()
        }
        manifest: Dict[str, str] = {
            path: self._hash_content(content)
            for path, content in sorted(normalized_files.items())
        }
        await self._ensure_blobs(normalized_files, manifest)
        return manifest, self._manifest_bundle_hash(manifest)

    async def materialize_revision_files(self, revision: PublishedAppRevision) -> Dict[str, str]:
        manifest = revision.manifest_json if isinstance(revision.manifest_json, dict) else {}
        if manifest:
            try:
                return await self.materialize_files_from_manifest(
                    {str(path): str(blob_hash) for path, blob_hash in manifest.items()}
                )
            except Exception:
                # Hard-cut versions can still contain inline files snapshots; if blob materialization
                # fails (missing metadata/object or unavailable storage), fall back to inline files.
                inline_files = {str(path): str(content) for path, content in dict(revision.files or {}).items()}
                if inline_files:
                    return inline_files
                raise
        return {str(path): str(content) for path, content in dict(revision.files or {}).items()}

    async def materialize_files_from_manifest(self, manifest: Dict[str, str]) -> Dict[str, str]:
        blobs_by_hash = await self._load_blob_rows(set(str(value) for value in manifest.values()))
        files: Dict[str, str] = {}
        for path, blob_hash in manifest.items():
            blob = blobs_by_hash.get(str(blob_hash))
            if blob is None:
                raise RuntimeError(f"Missing revision blob metadata for hash `{blob_hash}`")
            if blob.inline_content is not None:
                files[str(path)] = str(blob.inline_content)
                continue
            if self._storage is None:
                raise RuntimeError(f"Revision blob storage is unavailable for hash `{blob_hash}`")
            payload, _ = self._storage.read_asset_bytes(
                dist_storage_prefix=REVISION_BLOB_PREFIX,
                asset_path=self._blob_asset_path(str(blob_hash)),
            )
            files[str(path)] = payload.decode("utf-8", errors="replace")
        return files

    async def _ensure_blobs(self, files: Dict[str, str], manifest: Dict[str, str]) -> None:
        required_hashes = set(manifest.values())
        existing = await self._load_blob_rows(required_hashes)
        pending_rows: list[dict[str, object]] = []
        seen_hashes: set[str] = set(existing)
        for path, content in sorted(files.items()):
            blob_hash = manifest[path]
            if blob_hash in seen_hashes:
                continue
            payload = content.encode("utf-8")
            storage_key = None
            inline_content = None
            if self._storage is None:
                inline_content = content
            else:
                try:
                    storage_key = self._storage.write_asset_bytes(
                        dist_storage_prefix=REVISION_BLOB_PREFIX,
                        asset_path=self._blob_asset_path(blob_hash),
                        payload=payload,
                        content_type="text/plain; charset=utf-8",
                        cache_control="public,max-age=31536000,immutable",
                    )
                except Exception:
                    # Local/dev test environments often have no reachable object storage endpoint.
                    # Fall back to inline blob persistence so revision snapshots still work.
                    inline_content = content
                    storage_key = None
            pending_rows.append(
                {
                    "blob_hash": blob_hash,
                    "storage_key": storage_key,
                    "inline_content": inline_content,
                    "size_bytes": len(payload),
                }
            )
            seen_hashes.add(blob_hash)
        if not pending_rows:
            return

        bind = self._db.get_bind()
        dialect_name = str(getattr(getattr(bind, "dialect", None), "name", "") or "").lower()
        try:
            if dialect_name == "postgresql":
                stmt = pg_insert(PublishedAppRevisionBlob).values(pending_rows).on_conflict_do_nothing(
                    index_elements=["blob_hash"]
                )
                await self._db.execute(stmt)
            elif dialect_name == "sqlite":
                stmt = sqlite_insert(PublishedAppRevisionBlob).values(pending_rows).on_conflict_do_nothing(
                    index_elements=["blob_hash"]
                )
                await self._db.execute(stmt)
            else:
                stmt = insert(PublishedAppRevisionBlob).values(pending_rows)
                await self._db.execute(stmt)
        except IntegrityError:
            # Concurrent materializers may race on the same blob hash in non-upsert-capable paths.
            pass

    async def _load_blob_rows(self, blob_hashes: set[str]) -> Dict[str, PublishedAppRevisionBlob]:
        if not blob_hashes:
            return {}
        result = await self._db.execute(
            select(PublishedAppRevisionBlob).where(PublishedAppRevisionBlob.blob_hash.in_(list(blob_hashes)))
        )
        rows = list(result.scalars().all())
        return {str(row.blob_hash): row for row in rows}
