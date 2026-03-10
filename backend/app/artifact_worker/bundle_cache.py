from __future__ import annotations

import io
import os
import shutil
import zipfile
from pathlib import Path
from dataclasses import dataclass
from uuid import uuid4

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
    dependency_cache_hit: bool


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
        dependency_marker = self._dependency_marker(target_dir=target_dir, dependency_hash=revision.dependency_hash)
        if marker.exists():
            dependency_cache_hit = dependency_marker is None or dependency_marker.exists()
            if dependency_marker is not None and not dependency_marker.exists():
                dependency_marker.write_text("ok", encoding="utf-8")
            return ArtifactBundleResolution(
                bundle_dir=target_dir,
                cache_hit=True,
                payload_source=self._payload_source(revision),
                dependency_cache_hit=dependency_cache_hit,
            )
        payload = self._read_bundle_payload(revision)
        temp_dir = self._cache_root / f"{bundle_hash}.tmp-{uuid4().hex}"
        shutil.rmtree(temp_dir, ignore_errors=True)
        shutil.rmtree(target_dir, ignore_errors=True)
        temp_dir.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
                archive.extractall(temp_dir)
            marker = temp_dir / ".ready"
            marker.write_text("ok", encoding="utf-8")
            dependency_marker = self._dependency_marker(target_dir=temp_dir, dependency_hash=revision.dependency_hash)
            if dependency_marker is not None:
                dependency_marker.write_text("ok", encoding="utf-8")
            temp_dir.rename(target_dir)
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise
        return ArtifactBundleResolution(
            bundle_dir=target_dir,
            cache_hit=False,
            payload_source=self._payload_source(revision),
            dependency_cache_hit=False,
        )

    def _read_bundle_payload(self, revision: ArtifactRevision) -> bytes:
        if revision.bundle_storage_key and self._storage is not None:
            return self._storage.read_bundle(storage_key=revision.bundle_storage_key)
        if revision.bundle_inline_bytes:
            return bytes(revision.bundle_inline_bytes)
        raise RuntimeError("Artifact bundle payload is unavailable")

    @staticmethod
    def _payload_source(revision: ArtifactRevision) -> str:
        if revision.bundle_storage_key:
            return "object_storage"
        if revision.bundle_inline_bytes:
            return "inline_db"
        return "unavailable"

    @staticmethod
    def _dependency_marker(*, target_dir: Path, dependency_hash: str | None) -> Path | None:
        normalized = str(dependency_hash or "").strip()
        if not normalized:
            return None
        return target_dir / f".dependency-ready-{normalized}"
