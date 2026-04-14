from __future__ import annotations

from pathlib import PurePosixPath
from typing import Mapping

try:
    from app.api.routers.published_apps_admin_shared import (
        BUILDER_ALLOWED_DIR_ROOTS,
        BUILDER_ALLOWED_EXTENSIONS,
        BUILDER_ALLOWED_ROOT_FILES,
        BUILDER_ALLOWED_ROOT_GLOBS,
        BUILDER_BLOCKED_DIR_PREFIXES,
    )
except Exception:
    BUILDER_ALLOWED_DIR_ROOTS = ()
    BUILDER_ALLOWED_EXTENSIONS = (
        ".css",
        ".html",
        ".js",
        ".json",
        ".jsx",
        ".md",
        ".mdx",
        ".mjs",
        ".mts",
        ".png",
        ".svg",
        ".ts",
        ".tsx",
        ".txt",
        ".webp",
        ".yaml",
        ".yml",
    )
    BUILDER_ALLOWED_ROOT_FILES = (
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "tsconfig.json",
        "vite.config.ts",
        "vite.config.js",
        "postcss.config.js",
        "postcss.config.cjs",
        "tailwind.config.js",
        "tailwind.config.ts",
        "components.json",
        ".env.example",
    )
    BUILDER_ALLOWED_ROOT_GLOBS = ()
    BUILDER_BLOCKED_DIR_PREFIXES = (
        "node_modules/",
        ".talmudpedia/",
        ".git/",
        ".next/",
        ".vite/",
        ".turbo/",
        ".cache/",
        ".parcel-cache/",
        ".npm/",
        ".pnpm-store/",
        ".yarn/",
        "dist/",
        "build/",
        "coverage/",
        "__pycache__/",
    )


BUILDER_SNAPSHOT_IGNORED_FILE_NAMES = {
    ".eslintcache",
    ".stylelintcache",
}
BUILDER_SNAPSHOT_IGNORED_SUFFIXES = (
    ".tsbuildinfo",
)


def normalize_builder_snapshot_path(raw_path: str) -> str | None:
    raw = str(raw_path or "").replace("\\", "/").strip()
    if not raw:
        return None
    if raw.startswith("/"):
        return None

    parts: list[str] = []
    for part in raw.split("/"):
        if not part or part == ".":
            continue
        if part == "..":
            return None
        parts.append(part)
    normalized = "/".join(parts)
    return normalized or None


def is_builder_snapshot_artifact_path(path: str) -> bool:
    lowered = str(path or "").strip().lower()
    if not lowered:
        return True
    segments = [segment for segment in lowered.split("/") if segment]
    if "node_modules" in segments:
        return True
    if lowered.startswith(".opencode/.bun/") or lowered == ".opencode/.bun":
        return True
    blocked_prefix = next(
        (
            prefix
            for prefix in BUILDER_BLOCKED_DIR_PREFIXES
            if lowered == prefix.rstrip("/") or lowered.startswith(prefix)
        ),
        None,
    )
    if blocked_prefix:
        return True

    filename = PurePosixPath(lowered).name
    if filename in BUILDER_SNAPSHOT_IGNORED_FILE_NAMES:
        return True
    if any(filename.endswith(suffix) for suffix in BUILDER_SNAPSHOT_IGNORED_SUFFIXES):
        return True
    return False


def filter_builder_snapshot_files(files: Mapping[str, object]) -> dict[str, str]:
    filtered: dict[str, str] = {}
    for raw_path, raw_content in files.items():
        if not isinstance(raw_path, str):
            continue
        normalized_path = normalize_builder_snapshot_path(raw_path)
        if not normalized_path:
            continue
        if is_builder_snapshot_artifact_path(normalized_path):
            continue
        filtered[normalized_path] = raw_content if isinstance(raw_content, str) else str(raw_content)
    return filtered


def is_builder_snapshot_allowed_path(path: str) -> bool:
    normalized_path = normalize_builder_snapshot_path(path)
    if not normalized_path:
        return False
    lowered = normalized_path.lower()
    segments = [segment for segment in lowered.split("/") if segment]
    if "node_modules" in segments:
        return False
    if lowered.startswith(".opencode/.bun/") or lowered == ".opencode/.bun":
        return False
    blocked_prefix = next(
        (
            prefix
            for prefix in BUILDER_BLOCKED_DIR_PREFIXES
            if lowered == prefix.rstrip("/") or lowered.startswith(prefix)
        ),
        None,
    )
    if blocked_prefix:
        return False
    if BUILDER_ALLOWED_DIR_ROOTS:
        in_allowed_dir = any(normalized_path.startswith(root) for root in BUILDER_ALLOWED_DIR_ROOTS)
        if not in_allowed_dir:
            is_root_file = "/" not in normalized_path
            matches_root_file = normalized_path in BUILDER_ALLOWED_ROOT_FILES
            matches_root_glob = any(PurePosixPath(normalized_path).match(pattern) for pattern in BUILDER_ALLOWED_ROOT_GLOBS)
            if not (is_root_file and (matches_root_file or matches_root_glob)):
                return False
    suffix = PurePosixPath(normalized_path).suffix.lower()
    return suffix in BUILDER_ALLOWED_EXTENSIONS


def filter_and_validate_builder_snapshot_files(files: Mapping[str, object]) -> dict[str, str]:
    filtered = filter_builder_snapshot_files(files)
    return {
        path: content
        for path, content in filtered.items()
        if is_builder_snapshot_allowed_path(path)
    }
