from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Tuple


TEMPLATE_MANIFEST_NAME = "template.manifest.json"
VITE_BASE_PATTERN = re.compile(r"base\s*:\s*['\"]\./['\"]")
TEMPLATE_PACKS_ROOT = Path(__file__).resolve().parent.parent / "templates" / "published_apps"


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
    for path in sorted(pack_dir.rglob("*")):
        if not path.is_file():
            continue
        rel_path = _normalize_file_path(pack_dir, path)
        if any(part.startswith(".") for part in Path(rel_path).parts):
            continue
        if rel_path == TEMPLATE_MANIFEST_NAME:
            continue
        files[rel_path] = path.read_text(encoding="utf-8")
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


@lru_cache(maxsize=1)
def _load_all_packs() -> Tuple[_TemplatePack, ...]:
    if not TEMPLATE_PACKS_ROOT.exists():
        raise ValueError(f"Template packs root not found: {TEMPLATE_PACKS_ROOT}")

    packs: List[_TemplatePack] = []
    seen_keys: set[str] = set()
    for path in sorted(TEMPLATE_PACKS_ROOT.iterdir()):
        if not path.is_dir():
            continue
        pack = _load_pack(path)
        if pack.template.key in seen_keys:
            raise ValueError(f"Duplicate template key found: {pack.template.key}")
        seen_keys.add(pack.template.key)
        packs.append(pack)

    if not packs:
        raise ValueError(f"No template packs found under: {TEMPLATE_PACKS_ROOT}")
    return tuple(packs)


def list_templates() -> List[PublishedAppTemplate]:
    return [pack.template for pack in _load_all_packs()]


def get_template(template_key: str) -> PublishedAppTemplate:
    for pack in _load_all_packs():
        if pack.template.key == template_key:
            return pack.template
    raise KeyError(template_key)


def build_template_files(template_key: str) -> Dict[str, str]:
    for pack in _load_all_packs():
        if pack.template.key == template_key:
            return dict(pack.files)
    raise KeyError(template_key)
