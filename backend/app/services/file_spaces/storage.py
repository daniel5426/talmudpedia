from __future__ import annotations

import os
from pathlib import Path

from app.services.published_app_bundle_storage import (
    PublishedAppBundleStorage,
    PublishedAppBundleStorageError,
    PublishedAppBundleStorageNotConfigured,
)


FILES_STORAGE_PREFIX = "file-spaces"


class FileSpaceStorageError(Exception):
    pass


class FileSpaceStorage:
    def __init__(self, *, base_dir: str | None = None) -> None:
        configured = str(base_dir or os.getenv("FILE_SPACE_STORAGE_DIR") or "").strip()
        self._base_dir = Path(configured or "/tmp/talmudpedia-file-spaces")
        self._base_dir.mkdir(parents=True, exist_ok=True)
        try:
            self._bundle_storage = PublishedAppBundleStorage.from_env()
        except PublishedAppBundleStorageNotConfigured:
            self._bundle_storage = None

    @staticmethod
    def build_storage_key(*, project_id: str, space_id: str, entry_id: str, revision_id: str, filename: str) -> str:
        safe_name = Path(filename or "file.bin").name or "file.bin"
        return f"{project_id}/{space_id}/{entry_id}/{revision_id}/{safe_name}"

    def write_bytes(
        self,
        *,
        project_id: str,
        space_id: str,
        entry_id: str,
        revision_id: str,
        filename: str,
        payload: bytes,
        content_type: str,
    ) -> str:
        storage_key = self.build_storage_key(
            project_id=project_id,
            space_id=space_id,
            entry_id=entry_id,
            revision_id=revision_id,
            filename=filename,
        )
        if self._bundle_storage is not None:
            try:
                self._bundle_storage.write_asset_bytes(
                    dist_storage_prefix=FILES_STORAGE_PREFIX,
                    asset_path=storage_key,
                    payload=payload,
                    content_type=content_type,
                    cache_control="private,max-age=31536000,immutable",
                )
                return storage_key
            except PublishedAppBundleStorageError:
                pass
        absolute_path = self._base_dir / storage_key
        absolute_path.parent.mkdir(parents=True, exist_ok=True)
        absolute_path.write_bytes(payload)
        return storage_key

    def read_bytes(self, *, storage_key: str) -> bytes:
        normalized = Path(str(storage_key or "").strip().lstrip("/")).as_posix().strip("/")
        if not normalized:
            raise FileSpaceStorageError("File storage key is invalid")
        if self._bundle_storage is not None:
            try:
                payload, _ = self._bundle_storage.read_asset_bytes(
                    dist_storage_prefix=FILES_STORAGE_PREFIX,
                    asset_path=normalized,
                )
                return payload
            except PublishedAppBundleStorageError:
                pass
        absolute_path = self._base_dir / normalized
        if not absolute_path.exists() or not absolute_path.is_file():
            raise FileSpaceStorageError("File content not found")
        return absolute_path.read_bytes()
