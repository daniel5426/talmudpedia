from __future__ import annotations

from pathlib import PurePosixPath
from typing import Mapping

try:
    from app.api.routers.published_apps_admin_shared import BUILDER_BLOCKED_DIR_PREFIXES
except Exception:
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
