from __future__ import annotations

import mimetypes
import os
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import List, Optional, Tuple


class PublishedAppBundleStorageError(Exception):
    pass


class PublishedAppBundleStorageNotConfigured(PublishedAppBundleStorageError):
    pass


class PublishedAppBundleAssetNotFound(PublishedAppBundleStorageError):
    pass


@dataclass(frozen=True)
class PublishedAppBundleStorageConfig:
    bucket: str
    region: Optional[str]
    endpoint: Optional[str]
    access_key: Optional[str]
    secret_key: Optional[str]


class PublishedAppBundleStorage:
    def __init__(self, config: PublishedAppBundleStorageConfig):
        self._config = config
        self._client = None

    @classmethod
    def from_env(cls) -> "PublishedAppBundleStorage":
        bucket = (os.getenv("APPS_BUNDLE_BUCKET") or "").strip()
        if not bucket:
            raise PublishedAppBundleStorageNotConfigured("APPS_BUNDLE_BUCKET is required")
        return cls(
            PublishedAppBundleStorageConfig(
                bucket=bucket,
                region=(os.getenv("APPS_BUNDLE_REGION") or "").strip() or None,
                endpoint=(os.getenv("APPS_BUNDLE_ENDPOINT") or "").strip() or None,
                access_key=(os.getenv("APPS_BUNDLE_ACCESS_KEY") or "").strip() or None,
                secret_key=(os.getenv("APPS_BUNDLE_SECRET_KEY") or "").strip() or None,
            )
        )

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            import boto3
        except Exception as exc:  # pragma: no cover - import guard
            raise PublishedAppBundleStorageError("boto3 is required for apps bundle storage") from exc

        kwargs = {
            "service_name": "s3",
            "region_name": self._config.region,
            "endpoint_url": self._config.endpoint,
        }
        if self._config.access_key:
            kwargs["aws_access_key_id"] = self._config.access_key
        if self._config.secret_key:
            kwargs["aws_secret_access_key"] = self._config.secret_key

        self._client = boto3.client(**kwargs)
        return self._client

    @staticmethod
    def build_revision_dist_prefix(*, tenant_id: str, app_id: str, revision_id: str) -> str:
        return f"apps/{tenant_id}/{app_id}/revisions/{revision_id}/dist"

    @staticmethod
    def _normalize_prefix(prefix: str) -> str:
        value = (prefix or "").strip().strip("/")
        if not value:
            raise PublishedAppBundleStorageError("Storage prefix is required")
        return value

    @staticmethod
    def _normalize_asset_path(asset_path: str) -> str:
        raw = (asset_path or "").replace("\\", "/").strip()
        if not raw:
            raise PublishedAppBundleStorageError("Asset path is required")
        if raw.startswith("/"):
            raise PublishedAppBundleStorageError("Absolute asset paths are not allowed")

        parts: List[str] = []
        for part in raw.split("/"):
            if not part or part == ".":
                continue
            if part == "..":
                raise PublishedAppBundleStorageError("Path traversal is not allowed")
            parts.append(part)

        normalized = "/".join(parts)
        if not normalized:
            raise PublishedAppBundleStorageError("Asset path is required")
        return normalized

    @classmethod
    def build_asset_key(cls, *, dist_storage_prefix: str, asset_path: str) -> str:
        prefix = cls._normalize_prefix(dist_storage_prefix)
        normalized_asset_path = cls._normalize_asset_path(asset_path)
        return f"{prefix}/{normalized_asset_path}"

    def copy_prefix(self, *, source_prefix: str, destination_prefix: str) -> int:
        source = self._normalize_prefix(source_prefix)
        destination = self._normalize_prefix(destination_prefix)

        if source == destination:
            return 0

        client = self._get_client()

        copied = 0
        continuation_token = None
        while True:
            kwargs = {
                "Bucket": self._config.bucket,
                "Prefix": f"{source}/",
                "MaxKeys": 1000,
            }
            if continuation_token:
                kwargs["ContinuationToken"] = continuation_token

            try:
                page = client.list_objects_v2(**kwargs)
            except Exception as exc:
                raise PublishedAppBundleStorageError(f"Failed to list source artifacts: {exc}") from exc

            for item in page.get("Contents", []) or []:
                source_key = str(item.get("Key") or "")
                if not source_key or source_key.endswith("/"):
                    continue
                suffix = source_key[len(source) :]
                destination_key = f"{destination}{suffix}"
                try:
                    client.copy_object(
                        Bucket=self._config.bucket,
                        Key=destination_key,
                        CopySource={"Bucket": self._config.bucket, "Key": source_key},
                    )
                except Exception as exc:
                    raise PublishedAppBundleStorageError(
                        f"Failed to copy artifact `{source_key}` to `{destination_key}`: {exc}"
                    ) from exc
                copied += 1

            if not page.get("IsTruncated"):
                break
            continuation_token = page.get("NextContinuationToken")
            if not continuation_token:
                break

        return copied

    def read_asset_bytes(self, *, dist_storage_prefix: str, asset_path: str) -> Tuple[bytes, str]:
        key = self.build_asset_key(dist_storage_prefix=dist_storage_prefix, asset_path=asset_path)
        client = self._get_client()
        try:
            response = client.get_object(Bucket=self._config.bucket, Key=key)
        except Exception as exc:
            error_message = str(exc)
            if "NoSuchKey" in error_message or "404" in error_message:
                raise PublishedAppBundleAssetNotFound(f"Asset not found: {asset_path}") from exc
            raise PublishedAppBundleStorageError(f"Failed to fetch asset `{asset_path}`: {exc}") from exc

        body = response.get("Body")
        if body is None:
            raise PublishedAppBundleAssetNotFound(f"Asset not found: {asset_path}")
        payload = body.read()

        content_type = (response.get("ContentType") or "").strip()
        if not content_type:
            guess, _ = mimetypes.guess_type(PurePosixPath(asset_path).name)
            content_type = guess or "application/octet-stream"
        return payload, content_type
