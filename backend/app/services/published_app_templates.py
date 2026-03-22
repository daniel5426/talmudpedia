from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


TEMPLATE_MANIFEST_NAME = "template.manifest.json"
DEFAULT_TEMPLATE_KEY = "classic-chat"
VITE_BASE_PATTERN = re.compile(r"base\s*:\s*['\"]\./['\"]")
TEMPLATE_PACKS_ROOT = Path(__file__).resolve().parent.parent / "templates" / "published_apps"
OPENCODE_BOOTSTRAP_ROOT = Path(__file__).resolve().parent.parent / "templates" / "published_app_bootstrap" / "opencode"
COMMON_BOOTSTRAP_ROOT = Path(__file__).resolve().parent.parent / "templates" / "published_app_bootstrap" / "common"
RUNTIME_SDK_PACKAGE_ROOT = Path(__file__).resolve().parents[3] / "packages" / "runtime-sdk"
OPENCODE_BOOTSTRAP_CONTEXT_PATH = ".cache/opencode/selected_agent_contract.json"
OPENCODE_BOOTSTRAP_REQUIRED_FILES = (
    ".opencode/package.json",
    ".opencode/tools/read_agent_context.ts",
)
COMMON_BOOTSTRAP_REQUIRED_FILES = (
    "src/runtime-sdk.ts",
    "src/runtime-config.json",
)
RUNTIME_SDK_REQUIRED_FILES = (
    "package.json",
    "src/index.ts",
)
IGNORED_TEMPLATE_DIRS = {"node_modules", "dist", "build", "__pycache__"}
IGNORED_TEMPLATE_FILE_NAMES = {"vite.config.js", "vite.config.d.ts"}
IGNORED_TEMPLATE_FILE_SUFFIXES = {".tsbuildinfo"}
RUNTIME_SDK_DEPENDENCY_VERSION = "file:runtime-sdk"
RUNTIME_CONFIG_PATH = "src/runtime-config.json"


@dataclass(frozen=True)
class PublishedAppTemplate:
    key: str
    name: str
    description: str
    thumbnail: str
    tags: List[str]
    entry_file: str
    style_tokens: Dict[str, str]


@dataclass(frozen=True)
class _TemplatePack:
    template: PublishedAppTemplate
    files: Dict[str, str]


@dataclass(frozen=True)
class TemplateRuntimeContext:
    app_id: str = ""
    app_slug: str = ""
    agent_id: str = ""
    api_base_url: str = "/api/py"


def _load_manifest(pack_dir: Path) -> PublishedAppTemplate:
    manifest_path = pack_dir / TEMPLATE_MANIFEST_NAME
    if not manifest_path.exists():
        raise ValueError(f"Template pack is missing manifest: {manifest_path}")

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    required_fields = ["key", "name", "description", "thumbnail", "tags", "entry_file"]
    for field_name in required_fields:
        if field_name not in payload:
            raise ValueError(f"Template manifest missing `{field_name}`: {manifest_path}")

    key = str(payload["key"]).strip()
    if not key:
        raise ValueError(f"Template manifest has empty key: {manifest_path}")
    if key != pack_dir.name:
        raise ValueError(f"Template manifest key `{key}` must match folder `{pack_dir.name}`")

    tags = payload["tags"]
    if not isinstance(tags, list) or not all(isinstance(item, str) for item in tags):
        raise ValueError(f"Template manifest `tags` must be a list of strings: {manifest_path}")

    style_tokens = payload.get("style_tokens") or {}
    if not isinstance(style_tokens, dict) or not all(
        isinstance(token_key, str) and isinstance(token_val, str)
        for token_key, token_val in style_tokens.items()
    ):
        raise ValueError(f"Template manifest `style_tokens` must be a string map: {manifest_path}")

    return PublishedAppTemplate(
        key=key,
        name=str(payload["name"]),
        description=str(payload["description"]),
        thumbnail=str(payload["thumbnail"]),
        tags=[str(item) for item in tags],
        entry_file=str(payload["entry_file"]),
        style_tokens={str(k): str(v) for k, v in style_tokens.items()},
    )


def _normalize_file_path(pack_dir: Path, file_path: Path) -> str:
    rel_path = file_path.relative_to(pack_dir).as_posix()
    if rel_path.startswith("../") or rel_path.startswith("/"):
        raise ValueError(f"Invalid template file path: {file_path}")
    return rel_path


def _load_template_files(pack_dir: Path) -> Dict[str, str]:
    files: Dict[str, str] = {}
    for current_dir, dir_names, file_names in pack_dir.walk(top_down=True):
        dir_names[:] = sorted(
            name
            for name in dir_names
            if not name.startswith(".") and name not in IGNORED_TEMPLATE_DIRS
        )
        for file_name in sorted(file_names):
            if file_name.startswith("."):
                continue
            path = current_dir / file_name
            rel_path = _normalize_file_path(pack_dir, path)
            if rel_path in IGNORED_TEMPLATE_FILE_NAMES:
                continue
            if any(rel_path.endswith(suffix) for suffix in IGNORED_TEMPLATE_FILE_SUFFIXES):
                continue
            if rel_path == TEMPLATE_MANIFEST_NAME:
                continue
            files[rel_path] = path.read_text(encoding="utf-8")
    return files


def _load_opencode_bootstrap_files(pack_dir: Path) -> Dict[str, str]:
    if not pack_dir.exists() or not pack_dir.is_dir():
        raise ValueError(f"OpenCode bootstrap root not found: {pack_dir}")

    files: Dict[str, str] = {}
    for path in sorted(pack_dir.rglob("*")):
        if not path.is_file():
            continue
        rel_path = _normalize_file_path(pack_dir, path)
        # Keep this loader narrowly scoped to reserved OpenCode bootstrap paths.
        if not rel_path.startswith(".opencode/"):
            continue
        files[rel_path] = path.read_text(encoding="utf-8")

    for required in OPENCODE_BOOTSTRAP_REQUIRED_FILES:
        if required not in files:
            raise ValueError(
                f"OpenCode bootstrap is missing required file `{required}` under: {pack_dir}"
            )
    return files


def _load_common_bootstrap_files(pack_dir: Path) -> Dict[str, str]:
    if not pack_dir.exists() or not pack_dir.is_dir():
        raise ValueError(f"Common bootstrap root not found: {pack_dir}")

    files: Dict[str, str] = {}
    for path in sorted(pack_dir.rglob("*")):
        if not path.is_file():
            continue
        rel_path = _normalize_file_path(pack_dir, path)
        if not rel_path.startswith("src/"):
            continue
        files[rel_path] = path.read_text(encoding="utf-8")

    for required in COMMON_BOOTSTRAP_REQUIRED_FILES:
        if required not in files:
            raise ValueError(
                f"Common bootstrap is missing required file `{required}` under: {pack_dir}"
            )
    return files


def _load_runtime_sdk_package_files(pack_dir: Path) -> Dict[str, str]:
    if not pack_dir.exists() or not pack_dir.is_dir():
        raise ValueError(f"Runtime SDK package root not found: {pack_dir}")

    files: Dict[str, str] = {}
    for path in sorted(pack_dir.rglob("*")):
        if not path.is_file():
            continue
        rel_path = _normalize_file_path(pack_dir, path)
        rel_parts = Path(rel_path).parts
        if any(part.startswith(".") for part in rel_parts):
            continue
        if any(part in IGNORED_TEMPLATE_DIRS for part in rel_parts):
            continue
        if rel_path == "package-lock.json":
            continue
        files[f"runtime-sdk/{rel_path}"] = path.read_text(encoding="utf-8")

    for required in RUNTIME_SDK_REQUIRED_FILES:
        expected = f"runtime-sdk/{required}"
        if expected not in files:
            raise ValueError(
                f"Runtime SDK package is missing required file `{required}` under: {pack_dir}"
            )
    return files


def _coerce_runtime_context(runtime_context: Optional[TemplateRuntimeContext | Dict[str, Any]]) -> TemplateRuntimeContext:
    if runtime_context is None:
        return TemplateRuntimeContext()
    if isinstance(runtime_context, TemplateRuntimeContext):
        return runtime_context
    if isinstance(runtime_context, dict):
        app_id = str(runtime_context.get("app_id") or "").strip()
        app_slug = str(runtime_context.get("app_slug") or "").strip()
        agent_id = str(runtime_context.get("agent_id") or "").strip()
        api_base_url = str(runtime_context.get("api_base_url") or "/api/py").strip() or "/api/py"
        return TemplateRuntimeContext(
            app_id=app_id,
            app_slug=app_slug,
            agent_id=agent_id,
            api_base_url=api_base_url,
        )
    raise ValueError("Unsupported runtime context type")


def _build_runtime_overlay_files(runtime_context: TemplateRuntimeContext) -> Dict[str, str]:
    bootstrap_path = ""
    if runtime_context.app_slug:
        bootstrap_path = f"/public/apps/{runtime_context.app_slug}/runtime/bootstrap"
    payload = {
        "app_id": runtime_context.app_id,
        "app_slug": runtime_context.app_slug,
        "agent_id": runtime_context.agent_id,
        "api_base_url": runtime_context.api_base_url,
        "bootstrap_path": bootstrap_path,
    }
    return {RUNTIME_CONFIG_PATH: json.dumps(payload, ensure_ascii=True, indent=2) + "\n"}


def _inject_runtime_sdk_dependency(files: Dict[str, str]) -> Dict[str, str]:
    package_path = "package.json"
    source = files.get(package_path)
    if source is None:
        return files

    try:
        payload = json.loads(source)
    except json.JSONDecodeError:
        return files
    if not isinstance(payload, dict):
        return files

    dependencies = payload.get("dependencies")
    if not isinstance(dependencies, dict):
        dependencies = {}
    dependencies["@talmudpedia/runtime-sdk"] = RUNTIME_SDK_DEPENDENCY_VERSION
    payload["dependencies"] = dependencies
    files[package_path] = json.dumps(payload, ensure_ascii=True, indent=2) + "\n"
    return files


def _validate_vite_base(pack_dir: Path, files: Dict[str, str]) -> None:
    vite_config_path = "vite.config.ts"
    if vite_config_path not in files:
        raise ValueError(f"Template pack is missing `{vite_config_path}`: {pack_dir}")

    vite_source = files[vite_config_path]
    if not VITE_BASE_PATTERN.search(vite_source):
        raise ValueError(f"Template `{pack_dir.name}` must set Vite base to './' in {vite_config_path}")


def _load_pack(pack_dir: Path) -> _TemplatePack:
    template = _load_manifest(pack_dir)
    files = _load_template_files(pack_dir)

    if template.entry_file not in files:
        raise ValueError(
            f"Template `{template.key}` entry_file `{template.entry_file}` does not exist in pack files"
        )

    _validate_vite_base(pack_dir, files)
    return _TemplatePack(template=template, files=files)


def _load_all_packs() -> Tuple[_TemplatePack, ...]:
    if not TEMPLATE_PACKS_ROOT.exists():
        raise ValueError(f"Template packs root not found: {TEMPLATE_PACKS_ROOT}")

    packs: List[_TemplatePack] = []
    seen_keys: set[str] = set()
    for path in sorted(TEMPLATE_PACKS_ROOT.iterdir()):
        if not path.is_dir():
            continue
        if not (path / TEMPLATE_MANIFEST_NAME).exists():
            continue
        pack = _load_pack(path)
        if pack.template.key in seen_keys:
            raise ValueError(f"Duplicate template key found: {pack.template.key}")
        seen_keys.add(pack.template.key)
        packs.append(pack)
    return tuple(packs)


def list_templates() -> List[PublishedAppTemplate]:
    return [pack.template for pack in _load_all_packs()]


def get_template(template_key: str) -> PublishedAppTemplate:
    for pack in _load_all_packs():
        if pack.template.key == template_key:
            return pack.template
    raise KeyError(template_key)


def build_template_files(
    template_key: str,
    runtime_context: Optional[TemplateRuntimeContext | Dict[str, Any]] = None,
) -> Dict[str, str]:
    resolved_runtime_context = _coerce_runtime_context(runtime_context)
    for pack in _load_all_packs():
        if pack.template.key == template_key:
            merged = dict(pack.files)
            merged.update(build_common_bootstrap_files())
            merged.update(build_opencode_bootstrap_files())
            merged.update(build_runtime_sdk_package_files())
            merged.update(_build_runtime_overlay_files(resolved_runtime_context))
            merged = _inject_runtime_sdk_dependency(merged)
            return merged
    raise KeyError(template_key)


def apply_runtime_bootstrap_overlay(
    files: Dict[str, str],
    runtime_context: Optional[TemplateRuntimeContext | Dict[str, Any]] = None,
) -> Dict[str, str]:
    resolved_runtime_context = _coerce_runtime_context(runtime_context)
    merged = dict(files or {})
    merged.update(build_common_bootstrap_files())
    merged.update(build_runtime_sdk_package_files())
    merged.update(_build_runtime_overlay_files(resolved_runtime_context))
    return _inject_runtime_sdk_dependency(merged)


def build_opencode_bootstrap_files() -> Dict[str, str]:
    return _load_opencode_bootstrap_files(OPENCODE_BOOTSTRAP_ROOT)


def build_common_bootstrap_files() -> Dict[str, str]:
    return _load_common_bootstrap_files(COMMON_BOOTSTRAP_ROOT)


def build_runtime_sdk_package_files() -> Dict[str, str]:
    return _load_runtime_sdk_package_files(RUNTIME_SDK_PACKAGE_ROOT)
