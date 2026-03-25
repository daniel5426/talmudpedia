from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.artifact_runtime import ArtifactRevision
from app.services.credentials_service import CredentialsService


CREDENTIAL_REFERENCE_RE = re.compile(r"@\{(?:[^{}|]*\|)?([0-9a-fA-F-]{36})\}")
DEFAULT_SECRET_FIELDS = ("api_key", "token", "secret", "access_token", "password")
PYTHON_STDLIB_MODULES = set(getattr(sys, "stdlib_module_names", set())) | {"__future__"}
JS_LITERAL_RE = re.compile(r"(?P<quote>['\"])@\{(?:[^{}|]*\|)?(?P<id>[0-9a-fA-F-]{36})\}(?P=quote)")


class ArtifactRuntimeSecretError(RuntimeError):
    pass


@dataclass(frozen=True)
class RuntimePreparedSource:
    source_files: list[dict[str, str]]
    credential_ids: list[str]


async def validate_and_collect_runtime_credential_refs(
    *,
    db: AsyncSession,
    tenant_id: UUID | None,
    language: str,
    source_files: list[dict[str, Any]] | None,
) -> list[str]:
    credential_ids = collect_runtime_credential_refs(language=language, source_files=source_files)
    if not credential_ids:
        return []
    await _resolve_scalar_secret_values(
        db=db,
        tenant_id=tenant_id,
        credential_ids=[UUID(item) for item in credential_ids],
    )
    return credential_ids


def validate_source_files_for_editor(
    *,
    language: str,
    source_files: list[dict[str, Any]] | None,
    dependencies: list[str] | None = None,
) -> list[dict[str, Any]]:
    normalized_language = str(language or "python").strip().lower()
    if normalized_language != "python":
        return []
    diagnostics: list[dict[str, Any]] = []
    parsed_trees: list[tuple[str, ast.AST]] = []
    for item in list(source_files or []):
        path = str((item or {}).get("path") or "")
        content = str((item or {}).get("content") or "")
        try:
            parsed_trees.append((path, ast.parse(content, filename=path)))
        except SyntaxError as exc:
            line = int(exc.lineno or 1)
            column = max(1, int(exc.offset or 1))
            diagnostics.append(
                {
                    "path": path,
                    "message": str(exc.msg or "Invalid Python syntax"),
                    "line": line,
                    "column": column,
                    "end_line": line,
                    "end_column": column + 1,
                    "severity": "error",
                    "code": "PYTHON_SYNTAX_ERROR",
                }
            )
    declared_dependencies = {
        _normalize_python_dependency_name(item)
        for item in list(dependencies or [])
        if _normalize_python_dependency_name(item)
    }
    local_modules = _collect_local_python_modules(source_files)
    for path, tree in parsed_trees:
        for node in ast.walk(tree):
            imported_names: list[tuple[str, int, int]] = []
            if isinstance(node, ast.Import):
                imported_names = [
                    (alias.name.split(".")[0], int(getattr(node, "lineno", 1) or 1), int(getattr(node, "col_offset", 0) or 0) + 1)
                    for alias in node.names
                ]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported_names = [
                    (str(node.module).split(".")[0], int(getattr(node, "lineno", 1) or 1), int(getattr(node, "col_offset", 0) or 0) + 1)
                ]
            for module_name, line, column in imported_names:
                normalized_module_name = _normalize_python_dependency_name(module_name)
                if (
                    not normalized_module_name
                    or normalized_module_name in PYTHON_STDLIB_MODULES
                    or normalized_module_name in local_modules
                    or normalized_module_name in declared_dependencies
                ):
                    continue
                diagnostics.append(
                    {
                        "path": path,
                        "message": f"Cannot resolve module '{module_name}'. Add it to artifact dependencies.",
                        "line": line,
                        "column": column,
                        "end_line": line,
                        "end_column": column + len(module_name),
                        "severity": "error",
                        "code": "PYTHON_MISSING_DEPENDENCY",
                    }
                )
    return diagnostics


def collect_runtime_credential_refs(*, language: str, source_files: list[dict[str, Any]] | None) -> list[str]:
    found: dict[str, str] = {}
    normalized_language = str(language or "python").strip().lower()
    for item in list(source_files or []):
        path = str((item or {}).get("path") or "")
        content = str((item or {}).get("content") or "")
        refs = (
            _collect_python_credential_refs(path=path, content=content)
            if normalized_language == "python"
            else _collect_js_credential_refs(path=path, content=content)
        )
        for credential_id in refs:
            found[credential_id] = credential_id
    return sorted(found.values())


def prepare_deployable_source_files(
    *,
    language: str,
    revision: ArtifactRevision,
) -> RuntimePreparedSource:
    credential_ids = list(((revision.manifest_json or {}).get("credential_refs") or []))
    rewritten_files = rewrite_source_files_for_context_credentials(
        language=language,
        source_files=list(revision.source_files or []),
    )
    return RuntimePreparedSource(source_files=rewritten_files, credential_ids=sorted(credential_ids))


async def resolve_runtime_credentials(
    *,
    db: AsyncSession,
    tenant_id: UUID | None,
    revision: ArtifactRevision,
) -> dict[str, str]:
    credential_ids = [UUID(item) for item in list(((revision.manifest_json or {}).get("credential_refs") or []))]
    return await _resolve_scalar_secret_values(
        db=db,
        tenant_id=tenant_id,
        credential_ids=credential_ids,
    )


def rewrite_source_files_for_context_credentials(
    *,
    language: str,
    source_files: list[dict[str, Any]] | None,
) -> list[dict[str, str]]:
    normalized_language = str(language or "python").strip().lower()
    rewritten: list[dict[str, str]] = []
    for item in list(source_files or []):
        path = str((item or {}).get("path") or "")
        content = str((item or {}).get("content") or "")
        if normalized_language == "python":
            rewritten_content = _rewrite_python_content(content=content, path=path)
        else:
            rewritten_content = _rewrite_js_content(content=content, path=path)
        rewritten.append({"path": path, "content": rewritten_content})
    return rewritten


async def _resolve_scalar_secret_values(
    *,
    db: AsyncSession,
    tenant_id: UUID | None,
    credential_ids: list[UUID],
) -> dict[str, str]:
    credentials = CredentialsService(db, tenant_id)
    resolved: dict[str, str] = {}
    for credential_id in credential_ids:
        credential = await credentials.get_by_id(credential_id)
        if credential is None:
            raise ArtifactRuntimeSecretError(f"Credential not found: {credential_id}")
        if not credential.is_enabled:
            raise ArtifactRuntimeSecretError(f"Credential disabled: {credential_id}")
        merged = await credentials.resolve_backend_config(
            {},
            credential_id,
            category=credential.category,
            provider_key=credential.provider_key,
            provider_variant=credential.provider_variant,
        )
        scalar = _default_scalar_secret(merged)
        if scalar is None:
            raise ArtifactRuntimeSecretError(f"Credential has no default scalar secret field: {credential_id}")
        resolved[str(credential_id)] = scalar
    return resolved


def _default_scalar_secret(payload: dict[str, Any] | None) -> str | None:
    for field_name in DEFAULT_SECRET_FIELDS:
        value = (payload or {}).get(field_name)
        if isinstance(value, str) and value:
            return value
    return None


def _normalize_python_dependency_name(raw: str | None) -> str:
    value = str(raw or "").strip().lower()
    if not value:
        return ""
    value = value.split("[", 1)[0].strip()
    for separator in ("==", ">=", "<=", "~=", "!=", ">", "<"):
        if separator in value:
            value = value.split(separator, 1)[0].strip()
    return value.replace("-", "_")


def _collect_local_python_modules(source_files: list[dict[str, Any]] | None) -> set[str]:
    modules: set[str] = set()
    for item in list(source_files or []):
        path = str((item or {}).get("path") or "").strip("/")
        if not path or not path.endswith(".py"):
            continue
        parts = [segment for segment in path.split("/") if segment]
        if not parts:
            continue
        if len(parts) == 1:
            modules.add(parts[0][:-3].lower())
            continue
        modules.add(parts[0].lower())
    return modules


def _collect_python_credential_refs(*, path: str, content: str) -> list[str]:
    try:
        tree = ast.parse(content, filename=path)
    except SyntaxError as exc:
        raise ArtifactRuntimeSecretError(f"Invalid Python source in `{path}`: {exc.msg}") from exc
    refs: dict[str, str] = {}
    supported_ranges: list[tuple[int, int]] = []
    parent_map = _build_parent_map(tree)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)) and _imports_runtime_sdk(node):
            raise ArtifactRuntimeSecretError(
                f"`artifact_runtime_sdk` is not supported in `{path}`. Use `@{{credential-id}}` directly in string literals."
            )
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        match = CREDENTIAL_REFERENCE_RE.fullmatch(node.value)
        if not match:
            continue
        if not _is_supported_literal_parent(node=node, parent_map=parent_map):
            raise ArtifactRuntimeSecretError(
                f"Unsupported credential reference usage in `{path}`. Only exact string-literal values like \"@{{credential-id}}\" are supported."
            )
        credential_id = _normalize_credential_id(match.group(1))
        refs[credential_id] = credential_id
        supported_ranges.append(
            (
                _line_col_to_index(content, node.lineno, node.col_offset),
                _line_col_to_index(content, node.end_lineno, node.end_col_offset),
            )
        )
    for match in CREDENTIAL_REFERENCE_RE.finditer(content):
        if not any(start <= match.start() and match.end() <= end for start, end in supported_ranges):
            raise ArtifactRuntimeSecretError(
                f"Unsupported credential reference usage in `{path}`. Only exact string-literal values like \"@{{credential-id}}\" are supported."
            )
    return sorted(refs.values())


def _rewrite_python_content(*, content: str, path: str) -> str:
    tree = ast.parse(content, filename=path)
    transformed = _PythonCredentialLiteralRewriter().visit(tree)
    ast.fix_missing_locations(transformed)
    return ast.unparse(transformed)


def _collect_js_credential_refs(*, path: str, content: str) -> list[str]:
    refs: dict[str, str] = {}
    supported_ranges: list[tuple[int, int]] = []
    for match in JS_LITERAL_RE.finditer(content):
        credential_id = _normalize_credential_id(match.group("id"))
        refs[credential_id] = credential_id
        supported_ranges.append(match.span())
    for match in CREDENTIAL_REFERENCE_RE.finditer(content):
        if not any(start <= match.start() and match.end() <= end for start, end in supported_ranges):
            raise ArtifactRuntimeSecretError(
                f"Unsupported credential reference usage in `{path}`. Only exact string-literal values like \"@{{credential-id}}\" are supported."
            )
    return sorted(refs.values())


def _rewrite_js_content(*, content: str, path: str) -> str:
    _collect_js_credential_refs(path=path, content=content)

    def _replace(match: re.Match[str]) -> str:
        credential_id = _normalize_credential_id(match.group("id"))
        return f'context.credentials["{credential_id}"]'

    return JS_LITERAL_RE.sub(_replace, content)


def _normalize_credential_id(raw: str) -> str:
    try:
        return str(UUID(str(raw)))
    except Exception as exc:
        raise ArtifactRuntimeSecretError("Invalid credential reference") from exc


def _build_parent_map(tree: ast.AST) -> dict[int, ast.AST]:
    parent_map: dict[int, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parent_map[id(child)] = parent
    return parent_map


def _imports_runtime_sdk(node: ast.Import | ast.ImportFrom) -> bool:
    if isinstance(node, ast.Import):
        return any(alias.name == "artifact_runtime_sdk" for alias in node.names)
    return str(node.module or "") == "artifact_runtime_sdk"


def _is_supported_literal_parent(*, node: ast.Constant, parent_map: dict[int, ast.AST]) -> bool:
    parent = parent_map.get(id(node))
    if isinstance(parent, ast.Dict):
        return node not in list(parent.keys or [])
    if isinstance(parent, ast.Expr):
        return False
    return True


def _line_col_to_index(content: str, lineno: int | None, col: int | None) -> int:
    if lineno is None or col is None:
        return 0
    lines = content.splitlines(keepends=True)
    if lineno <= 1:
        return int(col)
    return sum(len(line) for line in lines[: lineno - 1]) + int(col)


class _PythonCredentialLiteralRewriter(ast.NodeTransformer):
    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        if not isinstance(node.value, str):
            return node
        match = CREDENTIAL_REFERENCE_RE.fullmatch(node.value)
        if not match:
            return node
        credential_id = _normalize_credential_id(match.group(1))
        return ast.copy_location(
            ast.Subscript(
                value=ast.Subscript(
                    value=ast.Name(id="context", ctx=ast.Load()),
                    slice=ast.Constant(value="credentials"),
                    ctx=ast.Load(),
                ),
                slice=ast.Constant(value=credential_id),
                ctx=ast.Load(),
            ),
            node,
        )
