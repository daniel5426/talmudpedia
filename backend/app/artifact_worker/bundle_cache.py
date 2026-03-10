from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path
from dataclasses import dataclass

from app.db.postgres.models.artifact_runtime import ArtifactRevision
from app.services.artifact_runtime.bundle_storage import (
    ArtifactBundleStorage,
    ArtifactBundleStorageNotConfigured,
)


@dataclass(frozen=True)
class ArtifactBundleResolution:
    bundle_dir: Path
    cache_hit: bool
    payload_source: str


class ArtifactBundleCache:
    def __init__(self) -> None:
        self._cache_root = Path(
            (os.getenv("ARTIFACT_WORKER_BUNDLE_CACHE_DIR") or "/tmp/talmudpedia-artifact-runtime-cache").strip()
        )
        self._cache_root.mkdir(parents=True, exist_ok=True)
        try:
            self._storage = ArtifactBundleStorage.from_env()
        except ArtifactBundleStorageNotConfigured:
            self._storage = None

    def ensure_bundle_dir(self, revision: ArtifactRevision) -> ArtifactBundleResolution:
        bundle_hash = str(revision.bundle_hash or "").strip()
        if not bundle_hash:
            raise RuntimeError("Artifact revision is missing bundle_hash")
        target_dir = self._cache_root / bundle_hash
        marker = target_dir / ".ready"
        if marker.exists():
            return ArtifactBundleResolution(
                bundle_dir=target_dir,
                cache_hit=True,
                payload_source=self._payload_source(revision),
            )
        payload = self._read_bundle_payload(revision)
        target_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
            archive.extractall(target_dir)
        marker.write_text("ok", encoding="utf-8")
        return ArtifactBundleResolution(
            bundle_dir=target_dir,
            cache_hit=False,
            payload_source=self._payload_source(revision),
        )

    def _read_bundle_payload(self, revision: ArtifactRevision) -> bytes:
        if revision.bundle_inline_bytes:
            return bytes(revision.bundle_inline_bytes)
        if revision.bundle_storage_key and self._storage is not None:
            return self._storage.read_bundle(storage_key=revision.bundle_storage_key)
        raise RuntimeError("Artifact bundle payload is unavailable")

    @staticmethod
    def _payload_source(revision: ArtifactRevision) -> str:
        if revision.bundle_inline_bytes:
            return "inline_db"
        if revision.bundle_storage_key:
            return "object_storage"
        return "unavailable"
