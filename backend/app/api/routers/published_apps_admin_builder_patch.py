import json
import re
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any, Dict, List, Optional

from app.services.apps_builder_dependency_policy import validate_builder_dependency_policy

from .published_apps_admin_builder_core import _builder_compile_error, _builder_policy_error
from .published_apps_admin_shared import (
    BUILDER_ALLOWED_DIR_ROOTS,
    BUILDER_ALLOWED_EXTENSIONS,
    BUILDER_ALLOWED_ROOT_FILES,
    BUILDER_ALLOWED_ROOT_GLOBS,
    BUILDER_LOCKFILE_NAMES,
    BUILDER_MAX_FILE_BYTES,
    BUILDER_MAX_FILES,
    BUILDER_MAX_LOCKFILE_BYTES,
    BUILDER_MAX_OPS,
    BUILDER_MAX_PROJECT_BYTES,
    BuilderPatchOp,
    IMPORT_RE,
)

def _normalize_builder_path(path: str) -> str:
    raw = (path or "").replace("\\", "/").strip()
    if not raw:
        raise _builder_policy_error("File path is required", field="path")
    if raw.startswith("/"):
        raise _builder_policy_error("Absolute paths are not allowed", field="path")

    parts: List[str] = []
    for part in raw.split("/"):
        if not part or part == ".":
            continue
        if part == "..":
            raise _builder_policy_error("Path traversal is not allowed", field="path")
        parts.append(part)
    normalized = "/".join(parts)
    if not normalized:
        raise _builder_policy_error("File path is required", field="path")
    return normalized


def _assert_builder_path_allowed(path: str, *, field: str = "path") -> None:
    in_allowed_dir = any(path.startswith(root) for root in BUILDER_ALLOWED_DIR_ROOTS)
    if not in_allowed_dir:
        is_root_file = "/" not in path
        matches_root_file = path in BUILDER_ALLOWED_ROOT_FILES
        matches_root_glob = any(PurePosixPath(path).match(pattern) for pattern in BUILDER_ALLOWED_ROOT_GLOBS)
        if not (is_root_file and (matches_root_file or matches_root_glob)):
            raise _builder_policy_error(
                "File path must be in src/, public/, or an allowed Vite root file",
                field=field,
            )

    suffix = PurePosixPath(path).suffix.lower()
    if suffix not in BUILDER_ALLOWED_EXTENSIONS:
        raise _builder_policy_error(
            f"Unsupported file extension: {suffix or '(none)'}",
            field=field,
        )


def _resolve_local_project_import(import_path: str, importer_path: str, files: Dict[str, str]) -> Optional[str]:
    importer_dir = PurePosixPath(importer_path).parent.as_posix()
    joined = PurePosixPath(importer_dir, import_path).as_posix()
    parts: List[str] = []
    for part in joined.split("/"):
        if not part or part == ".":
            continue
        if part == "..":
            if not parts:
                return None
            parts.pop()
            continue
        parts.append(part)
    normalized = "/".join(parts)
    if not normalized:
        return None
    candidates = [
        normalized,
        f"{normalized}.tsx",
        f"{normalized}.ts",
        f"{normalized}.mts",
        f"{normalized}.cts",
        f"{normalized}.jsx",
        f"{normalized}.js",
        f"{normalized}.css",
        f"{normalized}/index.tsx",
        f"{normalized}/index.ts",
        f"{normalized}/index.mts",
        f"{normalized}/index.cts",
        f"{normalized}/index.jsx",
        f"{normalized}/index.js",
    ]
    for candidate in candidates:
        if candidate in files:
            return candidate
    return None


def _validate_builder_project_or_raise(files: Dict[str, str], entry_file: str) -> List[Dict[str, str]]:
    diagnostics: List[Dict[str, str]] = []

    if entry_file not in files:
        raise _builder_compile_error(
            "Entry file does not exist in project",
            diagnostics=[{"path": entry_file, "message": "Entry file is missing"}],
        )

    if len(files) > BUILDER_MAX_FILES:
        raise _builder_policy_error(
            f"Too many files in draft (limit: {BUILDER_MAX_FILES})",
            field="files",
        )

    total_size = 0
    for path, content in files.items():
        _assert_builder_path_allowed(path, field="files")
        encoded_size = len(content.encode("utf-8"))
        max_bytes = BUILDER_MAX_LOCKFILE_BYTES if path in BUILDER_LOCKFILE_NAMES else BUILDER_MAX_FILE_BYTES
        if encoded_size > max_bytes:
            raise _builder_policy_error(
                f"File exceeds size limit ({max_bytes} bytes): {path}",
                field="files",
            )
        total_size += encoded_size
    if total_size > BUILDER_MAX_PROJECT_BYTES:
        raise _builder_policy_error(
            f"Project exceeds size limit ({BUILDER_MAX_PROJECT_BYTES} bytes)",
            field="files",
        )

    code_files = [
        path for path in files.keys()
        if PurePosixPath(path).suffix.lower() in {".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs"}
    ]
    for path in code_files:
        source = files.get(path, "")
        for match in IMPORT_RE.findall(source):
            spec = match.strip()
            if not spec:
                continue
            if spec.startswith("."):
                if _resolve_local_project_import(spec, path, files) is None:
                    diagnostics.append({"path": path, "message": f"Unresolved local import: {spec}"})

    diagnostics.extend(validate_builder_dependency_policy(files))

    if diagnostics:
        raise _builder_compile_error("Project validation failed", diagnostics=diagnostics)
    return diagnostics


def _coerce_files_payload(files: Dict[str, str]) -> Dict[str, str]:
    normalized: Dict[str, str] = {}
    for raw_path, raw_content in files.items():
        path = _normalize_builder_path(raw_path)
        _assert_builder_path_allowed(path, field="files")
        content = raw_content if isinstance(raw_content, str) else json.dumps(raw_content)
        normalized[path] = content
    return normalized


def _apply_patch_operations(
    files: Dict[str, str],
    entry_file: str,
    operations: List[BuilderPatchOp],
) -> tuple[Dict[str, str], str]:
    if len(operations) > BUILDER_MAX_OPS:
        raise _builder_policy_error(
            f"Too many patch operations (limit: {BUILDER_MAX_OPS})",
            field="operations",
        )

    next_files = dict(files)
    next_entry = _normalize_builder_path(entry_file)
    _assert_builder_path_allowed(next_entry, field="entry_file")
    for operation in operations:
        if operation.op == "upsert_file":
            if not operation.path:
                raise _builder_policy_error("upsert_file requires path", field="operations.path")
            normalized_path = _normalize_builder_path(operation.path)
            _assert_builder_path_allowed(normalized_path, field="operations.path")
            next_files[normalized_path] = operation.content or ""
        elif operation.op == "delete_file":
            if not operation.path:
                raise _builder_policy_error("delete_file requires path", field="operations.path")
            normalized_path = _normalize_builder_path(operation.path)
            _assert_builder_path_allowed(normalized_path, field="operations.path")
            next_files.pop(normalized_path, None)
            if next_entry == normalized_path:
                next_entry = "src/main.tsx"
        elif operation.op == "rename_file":
            if not operation.from_path or not operation.to_path:
                raise _builder_policy_error(
                    "rename_file requires from_path and to_path",
                    field="operations.path",
                )
            from_path = _normalize_builder_path(operation.from_path)
            to_path = _normalize_builder_path(operation.to_path)
            _assert_builder_path_allowed(from_path, field="operations.from_path")
            _assert_builder_path_allowed(to_path, field="operations.to_path")
            if from_path not in next_files:
                raise _builder_policy_error(
                    f"rename_file source does not exist: {from_path}",
                    field="operations.from_path",
                )
            if to_path in next_files and to_path != from_path:
                raise _builder_policy_error(
                    f"rename_file target already exists: {to_path}",
                    field="operations.to_path",
                )
            next_files[to_path] = next_files.pop(from_path)
            if next_entry == from_path:
                next_entry = to_path
        elif operation.op == "set_entry_file":
            if not operation.entry_file:
                raise _builder_policy_error("set_entry_file requires entry_file", field="operations.entry_file")
            next_entry = _normalize_builder_path(operation.entry_file)
            _assert_builder_path_allowed(next_entry, field="operations.entry_file")

    if next_entry not in next_files:
        raise _builder_policy_error("entry_file must exist in files", field="entry_file")
    _validate_builder_project_or_raise(next_files, next_entry)
    return next_files, next_entry


def _sanitize_prompt_text(text: str, limit: int = 120) -> str:
    collapsed = " ".join(text.strip().split())
    if not collapsed:
        return ""
    return collapsed[:limit]


def _build_builder_patch_from_prompt(
    user_prompt: str,
    files: Dict[str, str],
) -> tuple[List[Dict[str, str]], str]:
    prompt = _sanitize_prompt_text(user_prompt, 140)
    prompt_lower = prompt.lower()
    patch_ops: List[Dict[str, str]] = []
    applied: List[str] = []

    app_source = files.get("src/App.tsx")
    if app_source is not None:
        updated_app = app_source

        if "Start a conversation." in updated_app:
            next_copy = f"Start a conversation. ({prompt})"
            next_app = updated_app.replace("Start a conversation.", next_copy, 1)
            if next_app != updated_app:
                updated_app = next_app
                applied.append("updated empty-state copy")

        if ("title" in prompt_lower or "rename" in prompt_lower or "name" in prompt_lower) and "const title = useMemo(() =>" in updated_app:
            title_text = prompt[:48].replace("\"", "'")
            next_app = re.sub(
                r'const title = useMemo\(\(\) => ".*?", \[\]\);',
                f'const title = useMemo(() => "{title_text}", []);',
                updated_app,
                count=1,
            )
            if next_app != updated_app:
                updated_app = next_app
                applied.append("updated app title")

        if "bold" in prompt_lower and "fontWeight: 700" not in updated_app:
            next_app = updated_app.replace(
                "fontSize: 16, fontFamily: theme.fontDisplay",
                "fontSize: 16, fontFamily: theme.fontDisplay, fontWeight: 700",
                1,
            )
            if next_app != updated_app:
                updated_app = next_app
                applied.append("made header title bold")

        if updated_app != app_source:
            patch_ops.append({"op": "upsert_file", "path": "src/App.tsx", "content": updated_app})

    theme_source = files.get("src/theme.ts")
    if theme_source is not None:
        color_map = {
            "blue": "#2563eb",
            "green": "#16a34a",
            "red": "#dc2626",
            "orange": "#ea580c",
            "teal": "#0f766e",
            "purple": "#7c3aed",
        }
        selected_color = next((hex_value for name, hex_value in color_map.items() if name in prompt_lower), None)
        if selected_color:
            next_theme = re.sub(
                r'accent:\s*".*?"',
                f'accent: "{selected_color}"',
                theme_source,
                count=1,
            )
            if next_theme != theme_source:
                patch_ops.append({"op": "upsert_file", "path": "src/theme.ts", "content": next_theme})
                applied.append(f"set accent color to {selected_color}")

    if not patch_ops and app_source is not None:
        timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        fallback_text = f"Start a conversation. ({prompt} · {timestamp})"
        next_app = app_source.replace("Start a conversation.", fallback_text, 1)
        if next_app == app_source:
            next_app = app_source.rstrip() + f"\n// Builder note: {prompt} ({timestamp})\n"
        patch_ops.append({"op": "upsert_file", "path": "src/App.tsx", "content": next_app})
        applied.append("applied fallback draft edit")

    summary = ", ".join(dict.fromkeys(applied)) if applied else "prepared a draft update"
    return patch_ops, summary
