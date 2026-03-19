from __future__ import annotations

import os
from pathlib import Path


class RuntimeAttachmentStorageError(Exception):
    pass


class RuntimeAttachmentStorage:
    def __init__(self, base_dir: str | None = None):
        configured = str(base_dir or os.getenv("RUNTIME_ATTACHMENT_STORAGE_DIR") or "").strip()
        if configured:
            self._base_dir = Path(configured)
        else:
            self._base_dir = Path("/tmp/talmudpedia-runtime-attachments")
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def write_bytes(self, *, attachment_id: str, filename: str, payload: bytes) -> str:
        safe_name = Path(filename or "attachment.bin").name
        relative_path = Path(attachment_id[:2]) / attachment_id / safe_name
        absolute_path = self._base_dir / relative_path
        absolute_path.parent.mkdir(parents=True, exist_ok=True)
        absolute_path.write_bytes(payload)
        return relative_path.as_posix()

    def read_bytes(self, *, storage_key: str) -> bytes:
        relative_path = Path(str(storage_key or "").strip().lstrip("/"))
        if not relative_path.parts:
            raise RuntimeAttachmentStorageError("Attachment storage key is invalid")
        absolute_path = self._base_dir / relative_path
        if not absolute_path.exists() or not absolute_path.is_file():
            raise RuntimeAttachmentStorageError("Attachment payload not found")
        return absolute_path.read_bytes()

    def delete_bytes(self, *, storage_key: str) -> None:
        relative_path = Path(str(storage_key or "").strip().lstrip("/"))
        if not relative_path.parts:
            return
        absolute_path = self._base_dir / relative_path
        try:
            absolute_path.unlink(missing_ok=True)
        except Exception:
            return
