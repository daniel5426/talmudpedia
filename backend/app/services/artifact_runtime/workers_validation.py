from __future__ import annotations

import os
import re


_REQ_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9_.-]*)")
_DEFAULT_BLOCKED = {
    "numpy",
    "pandas",
    "scipy",
    "torch",
    "tensorflow",
    "opencv-python",
    "psycopg2",
    "lxml",
}


class ArtifactWorkersCompatibilityError(ValueError):
    pass


def validate_workers_compatibility(*, source_files: list[dict[str, str]], python_dependencies: list[str]) -> None:
    _validate_source_files(source_files)
    _validate_dependencies(python_dependencies)


def _validate_source_files(source_files: list[dict[str, str]]) -> None:
    for item in source_files:
        path = str(item.get("path") or "").strip()
        if not path:
            raise ArtifactWorkersCompatibilityError("Artifact source file path is required")
        if path.startswith("/") or ".." in path.split("/"):
            raise ArtifactWorkersCompatibilityError(f"Artifact source file path `{path}` is invalid")
        if not path.endswith(".py"):
            raise ArtifactWorkersCompatibilityError("Only Python source files are supported in Workers artifact runtime v1")


def _validate_dependencies(dependencies: list[str]) -> None:
    allowlist = {
        item.strip().lower()
        for item in (os.getenv("ARTIFACT_WORKERS_ALLOWED_DEPENDENCIES") or "").split(",")
        if item.strip()
    }
    for requirement in dependencies or []:
        match = _REQ_NAME_RE.match(str(requirement or ""))
        if not match:
            raise ArtifactWorkersCompatibilityError(f"Dependency `{requirement}` is invalid")
        package_name = match.group(1).lower()
        if package_name in _DEFAULT_BLOCKED:
            raise ArtifactWorkersCompatibilityError(
                f"Dependency `{package_name}` is not supported by the Workers artifact runtime"
            )
        if allowlist and package_name not in allowlist:
            raise ArtifactWorkersCompatibilityError(
                f"Dependency `{package_name}` is not in the configured Workers dependency allowlist"
            )
