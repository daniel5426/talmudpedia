from __future__ import annotations

import os
from dataclasses import dataclass

from app.services.published_app_bundle_storage import (
    PublishedAppBundleStorage,
    PublishedAppBundleStorageConfig,
    PublishedAppBundleStorageError,
)


class ArtifactBundleStorageNotConfigured(PublishedAppBundleStorageError):
    pass


@dataclass(frozen=True)
class ArtifactBundleStorageLocation:
    storage_key: str
    bundle_hash: str


class ArtifactBundleStorage:
    BUNDLE_PREFIX = "artifacts/runtime-bundles"

    def __init__(self, storage: PublishedAppBundleStorage):
        self._storage = storage

    @classmethod
    def from_env(cls) -> "ArtifactBundleStorage":
        bucket = (
            (os.getenv("ARTIFACT_BUNDLE_BUCKET") or "").strip()
            or (os.getenv("APPS_BUNDLE_BUCKET") or "").strip()
        )
        if not bucket:
            raise ArtifactBundleStorageNotConfigured("ARTIFACT_BUNDLE_BUCKET or APPS_BUNDLE_BUCKET is required")
        storage = PublishedAppBundleStorage(
            PublishedAppBundleStorageConfig(
                bucket=bucket,
                region=(os.getenv("ARTIFACT_BUNDLE_REGION") or os.getenv("APPS_BUNDLE_REGION") or "").strip() or None,
                endpoint=(os.getenv("ARTIFACT_BUNDLE_ENDPOINT") or os.getenv("APPS_BUNDLE_ENDPOINT") or "").strip() or None,
                access_key=(os.getenv("ARTIFACT_BUNDLE_ACCESS_KEY") or os.getenv("APPS_BUNDLE_ACCESS_KEY") or "").strip() or None,
                secret_key=(os.getenv("ARTIFACT_BUNDLE_SECRET_KEY") or os.getenv("APPS_BUNDLE_SECRET_KEY") or "").strip() or None,
            )
        )
        return cls(storage)

    @classmethod
    def build_bundle_prefix(cls, *, organization_id: str, artifact_id: str | None, revision_id: str) -> str:
        artifact_segment = artifact_id or "ephemeral"
        return f"{cls.BUNDLE_PREFIX}/{organization_id}/{artifact_segment}/{revision_id}"

    def write_bundle(
        self,
        *,
        organization_id: str,
        artifact_id: str | None,
        revision_id: str,
        bundle_hash: str,
        payload: bytes,
    ) -> ArtifactBundleStorageLocation:
        prefix = self.build_bundle_prefix(organization_id=organization_id, artifact_id=artifact_id, revision_id=revision_id)
        storage_key = self._storage.write_asset_bytes(
            dist_storage_prefix=prefix,
            asset_path="bundle.zip",
            payload=payload,
            content_type="application/zip",
            cache_control="public,max-age=31536000,immutable",
        )
        return ArtifactBundleStorageLocation(storage_key=storage_key, bundle_hash=bundle_hash)

    def read_bundle(self, *, storage_key: str) -> bytes:
        normalized_key = str(storage_key or "").strip().strip("/")
        if not normalized_key or "/" not in normalized_key:
            raise PublishedAppBundleStorageError("Artifact bundle storage key is invalid")
        prefix, asset_path = normalized_key.rsplit("/", 1)
        payload, _content_type = self._storage.read_asset_bytes(
            dist_storage_prefix=prefix,
            asset_path=asset_path,
        )
        return payload
