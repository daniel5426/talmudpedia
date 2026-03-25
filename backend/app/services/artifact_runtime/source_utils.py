from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any


DEFAULT_ENTRY_MODULE_PATH = "main.py"


@dataclass(frozen=True)
class NormalizedArtifactSource:
    source_files: list[dict[str, str]]
    entry_module_path: str


def normalize_artifact_source(
    *,
    source_files: list[dict[str, Any]] | None = None,
    entry_module_path: str | None = None,
) -> NormalizedArtifactSource:
    normalized_entry = str(entry_module_path or DEFAULT_ENTRY_MODULE_PATH).strip() or DEFAULT_ENTRY_MODULE_PATH
    normalized_files: list[dict[str, str]] = []
    seen_paths: set[str] = set()

    for item in source_files or []:
        path = str((item or {}).get("path") or "").strip()
        if not path or path in seen_paths:
            continue
        content = str((item or {}).get("content") or "")
        seen_paths.add(path)
        normalized_files.append({"path": path, "content": content})

    if not normalized_files:
        raise ValueError("source_files is required")
    if normalized_entry not in {item["path"] for item in normalized_files}:
        raise ValueError(f"entry_module_path `{normalized_entry}` must exist in source_files")
    return NormalizedArtifactSource(
        source_files=normalized_files,
        entry_module_path=normalized_entry,
    )


def source_tree_hash(
    *,
    source_files: list[dict[str, Any]],
    entry_module_path: str,
    dependencies: list[str] | None,
    language: str = "python",
    runtime_wrapper_version: str = "cloudflare-workers-v1",
    compatibility_date: str | None = None,
    compatibility_flags: list[str] | None = None,
) -> str:
    canonical = {
        "language": str(language or "python"),
        "entry_module_path": str(entry_module_path or DEFAULT_ENTRY_MODULE_PATH),
        "dependencies": [str(item).strip() for item in dependencies or [] if str(item).strip()],
        "runtime_wrapper_version": runtime_wrapper_version,
        "compatibility_date": str(compatibility_date or ""),
        "compatibility_flags": [str(item).strip() for item in compatibility_flags or [] if str(item).strip()],
        "source_files": [
            {"path": str(item.get("path") or "").strip(), "content": str(item.get("content") or "")}
            for item in sorted(source_files, key=lambda value: str(value.get("path") or ""))
            if str(item.get("path") or "").strip()
        ],
    }
    return sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
