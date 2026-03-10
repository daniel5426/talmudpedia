from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import importlib.metadata as importlib_metadata
import json
from pathlib import Path, PurePosixPath
import re
from typing import Iterable


_DIST_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9_.-]*)")


@dataclass(frozen=True)
class PackagedDependencyFile:
    archive_path: str
    source_path: Path


@dataclass(frozen=True)
class PackagedDependencyManifest:
    declared: list[str]
    resolved: list[dict[str, str]]
    unresolved: list[str]
    files: list[PackagedDependencyFile]
    dependency_hash: str


def package_python_dependencies(requirements: Iterable[str] | None) -> PackagedDependencyManifest:
    declared = _normalize_requirements(requirements)
    dependency_hash = sha256(
        json.dumps(declared, ensure_ascii=True, separators=(",", ":"), sort_keys=False).encode("utf-8")
    ).hexdigest()

    resolved: list[dict[str, str]] = []
    unresolved: list[str] = []
    files: list[PackagedDependencyFile] = []
    seen_archive_paths: set[str] = set()

    for requirement in declared:
        distribution_name = _extract_distribution_name(requirement)
        if not distribution_name:
            unresolved.append(requirement)
            continue
        try:
            distribution = importlib_metadata.distribution(distribution_name)
        except importlib_metadata.PackageNotFoundError:
            unresolved.append(requirement)
            continue

        top_levels = _top_level_entries(distribution)
        if not top_levels:
            unresolved.append(requirement)
            continue

        resolved.append(
            {
                "declared": requirement,
                "distribution": str(distribution.metadata.get("Name") or distribution_name),
                "version": str(distribution.version or ""),
            }
        )

        base_path = Path(distribution.locate_file(""))
        for top_level in top_levels:
            root = base_path / top_level
            if not root.exists():
                continue
            for item in _iter_dependency_files(root):
                archive_path = str(PurePosixPath("vendor") / item.relative_to(base_path).as_posix())
                if archive_path in seen_archive_paths:
                    continue
                seen_archive_paths.add(archive_path)
                files.append(PackagedDependencyFile(archive_path=archive_path, source_path=item))

    return PackagedDependencyManifest(
        declared=declared,
        resolved=resolved,
        unresolved=sorted(set(unresolved)),
        files=files,
        dependency_hash=dependency_hash,
    )


def build_dependency_manifest_payload(packaged: PackagedDependencyManifest) -> dict[str, object]:
    return {
        "declared": list(packaged.declared),
        "resolved": list(packaged.resolved),
        "unresolved": list(packaged.unresolved),
        "dependency_hash": packaged.dependency_hash,
    }


def _normalize_requirements(requirements: Iterable[str] | None) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for item in requirements or []:
        requirement = str(item or "").strip()
        if not requirement or requirement in seen:
            continue
        seen.add(requirement)
        normalized.append(requirement)
    return normalized


def _extract_distribution_name(requirement: str) -> str | None:
    match = _DIST_NAME_RE.match(str(requirement or ""))
    if not match:
        return None
    return match.group(1)


def _top_level_entries(distribution: importlib_metadata.Distribution) -> list[str]:
    top_level_text = distribution.read_text("top_level.txt") or ""
    top_levels = [line.strip() for line in top_level_text.splitlines() if line.strip()]
    if top_levels:
        return top_levels

    candidate = _extract_distribution_name(str(distribution.metadata.get("Name") or ""))
    if not candidate:
        return []
    fallback = candidate.replace("-", "_").replace(".", "_")
    return [fallback]


def _iter_dependency_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts:
            continue
        files.append(path)
    return files
