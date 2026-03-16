from __future__ import annotations

import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from pathlib import PurePosixPath
from typing import List, Optional, Tuple
from urllib.parse import urlparse


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
    local_dir: Optional[str]
    allow_local_fallback: bool = False


class PublishedAppBundleStorage:
    def __init__(self, config: PublishedAppBundleStorageConfig):
        self._config = config
        self._client = None

    @classmethod
    def from_env(cls) -> "PublishedAppBundleStorage":
        bucket = (os.getenv("APPS_BUNDLE_BUCKET") or "").strip()
        if not bucket:
            raise PublishedAppBundleStorageNotConfigured("APPS_BUNDLE_BUCKET is required")
        endpoint = (os.getenv("APPS_BUNDLE_ENDPOINT") or "").strip() or None
        local_dir = (os.getenv("APPS_BUNDLE_LOCAL_DIR") or "").strip() or None
        allow_local_fallback = False
        if endpoint:
            parsed = urlparse(endpoint)
            if parsed.hostname in {"127.0.0.1", "localhost"}:
                allow_local_fallback = True
        if allow_local_fallback and not local_dir:
            local_dir = "/tmp/talmudpedia-apps-bundles"
        return cls(
            PublishedAppBundleStorageConfig(
                bucket=bucket,
                region=(os.getenv("APPS_BUNDLE_REGION") or "").strip() or None,
                endpoint=endpoint,
                access_key=(os.getenv("APPS_BUNDLE_ACCESS_KEY") or "").strip() or None,
                secret_key=(os.getenv("APPS_BUNDLE_SECRET_KEY") or "").strip() or None,
                local_dir=local_dir,
                allow_local_fallback=allow_local_fallback,
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
    def build_workspace_build_dist_prefix(*, tenant_id: str, app_id: str, workspace_build_id: str) -> str:
        return f"apps/{tenant_id}/{app_id}/workspace-builds/{workspace_build_id}/dist"

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

    def _local_asset_path(self, *, key: str) -> Path:
        local_dir = str(self._config.local_dir or "").strip()
        if not local_dir:
            raise PublishedAppBundleStorageError("Local bundle storage directory is not configured")
        return Path(local_dir).resolve() / key

    def _write_local_asset_bytes(self, *, key: str, payload: bytes) -> str:
        path = self._local_asset_path(key=key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return key

    def _read_local_asset_bytes(self, *, key: str) -> bytes:
        path = self._local_asset_path(key=key)
        if not path.exists() or not path.is_file():
            raise PublishedAppBundleAssetNotFound(f"Asset not found: {key}")
        return path.read_bytes()

    def _copy_local_prefix(self, *, source_prefix: str, destination_prefix: str) -> int:
        source_root = self._local_asset_path(key=f"{self._normalize_prefix(source_prefix)}/__placeholder__").parent
        destination_root = self._local_asset_path(key=f"{self._normalize_prefix(destination_prefix)}/__placeholder__").parent
        if not source_root.exists():
            return 0
        copied = 0
        for file_path in sorted(source_root.rglob("*")):
            if not file_path.is_file():
                continue
            relative = file_path.relative_to(source_root)
            target = destination_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(file_path.read_bytes())
            copied += 1
        return copied

    def copy_prefix(self, *, source_prefix: str, destination_prefix: str) -> int:
        source = self._normalize_prefix(source_prefix)
        destination = self._normalize_prefix(destination_prefix)

        if source == destination:
            return 0

        try:
            client = self._get_client()
        except PublishedAppBundleStorageError:
            if self._config.allow_local_fallback and self._config.local_dir:
                return self._copy_local_prefix(source_prefix=source, destination_prefix=destination)
            raise

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
                if self._config.allow_local_fallback and self._config.local_dir:
                    return self._copy_local_prefix(source_prefix=source, destination_prefix=destination)
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

    def write_asset_bytes(
        self,
        *,
        dist_storage_prefix: str,
        asset_path: str,
        payload: bytes,
        content_type: Optional[str] = None,
        cache_control: Optional[str] = None,
    ) -> str:
        key = self.build_asset_key(dist_storage_prefix=dist_storage_prefix, asset_path=asset_path)
        try:
            client = self._get_client()
        except PublishedAppBundleStorageError as exc:
            if self._config.allow_local_fallback and self._config.local_dir:
                return self._write_local_asset_bytes(key=key, payload=payload)
            raise exc
        resolved_content_type = content_type or mimetypes.guess_type(PurePosixPath(asset_path).name)[0] or "application/octet-stream"
        kwargs = {
            "Bucket": self._config.bucket,
            "Key": key,
            "Body": payload,
            "ContentType": resolved_content_type,
        }
        if cache_control:
            kwargs["CacheControl"] = cache_control
        try:
            client.put_object(**kwargs)
        except Exception as exc:
            if self._config.allow_local_fallback and self._config.local_dir:
                return self._write_local_asset_bytes(key=key, payload=payload)
            raise PublishedAppBundleStorageError(f"Failed to upload asset `{asset_path}`: {exc}") from exc
        return key

    def read_asset_bytes(self, *, dist_storage_prefix: str, asset_path: str) -> Tuple[bytes, str]:
        key = self.build_asset_key(dist_storage_prefix=dist_storage_prefix, asset_path=asset_path)
        try:
            client = self._get_client()
        except PublishedAppBundleStorageError as exc:
            if self._config.allow_local_fallback and self._config.local_dir:
                payload = self._read_local_asset_bytes(key=key)
                content_type = mimetypes.guess_type(PurePosixPath(asset_path).name)[0] or "application/octet-stream"
                return payload, content_type
            raise exc
        try:
            response = client.get_object(Bucket=self._config.bucket, Key=key)
        except Exception as exc:
            error_message = str(exc)
            if "NoSuchKey" in error_message or "404" in error_message:
                if self._config.allow_local_fallback and self._config.local_dir:
                    payload = self._read_local_asset_bytes(key=key)
                    content_type = mimetypes.guess_type(PurePosixPath(asset_path).name)[0] or "application/octet-stream"
                    return payload, content_type
                raise PublishedAppBundleAssetNotFound(f"Asset not found: {asset_path}") from exc
            if self._config.allow_local_fallback and self._config.local_dir:
                try:
                    payload = self._read_local_asset_bytes(key=key)
                    content_type = mimetypes.guess_type(PurePosixPath(asset_path).name)[0] or "application/octet-stream"
                    return payload, content_type
                except PublishedAppBundleAssetNotFound:
                    pass
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
