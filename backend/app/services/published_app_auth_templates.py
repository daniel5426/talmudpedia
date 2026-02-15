from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple


AUTH_TEMPLATE_MANIFEST_NAME = "auth_template.manifest.json"
AUTH_TEMPLATE_PACKS_ROOT = Path(__file__).resolve().parent.parent / "templates" / "published_app_auth"


@dataclass(frozen=True)
class PublishedAppAuthTemplate:
    key: str
    name: str
    description: str
    thumbnail: str
    tags: List[str]
    style_tokens: Dict[str, str]


def _load_manifest(pack_dir: Path) -> PublishedAppAuthTemplate:
    manifest_path = pack_dir / AUTH_TEMPLATE_MANIFEST_NAME
    if not manifest_path.exists():
        raise ValueError(f"Auth template pack is missing manifest: {manifest_path}")

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    required_fields = ["key", "name", "description", "thumbnail", "tags"]
    for field_name in required_fields:
        if field_name not in payload:
            raise ValueError(f"Auth template manifest missing `{field_name}`: {manifest_path}")

    key = str(payload["key"]).strip()
    if not key:
        raise ValueError(f"Auth template manifest has empty key: {manifest_path}")
    if key != pack_dir.name:
        raise ValueError(f"Auth template manifest key `{key}` must match folder `{pack_dir.name}`")

    tags = payload["tags"]
    if not isinstance(tags, list) or not all(isinstance(item, str) for item in tags):
        raise ValueError(f"Auth template manifest `tags` must be a list of strings: {manifest_path}")

    style_tokens = payload.get("style_tokens") or {}
    if not isinstance(style_tokens, dict) or not all(
        isinstance(token_key, str) and isinstance(token_val, str)
        for token_key, token_val in style_tokens.items()
    ):
        raise ValueError(f"Auth template manifest `style_tokens` must be a string map: {manifest_path}")

    return PublishedAppAuthTemplate(
        key=key,
        name=str(payload["name"]).strip(),
        description=str(payload["description"]).strip(),
        thumbnail=str(payload["thumbnail"]).strip(),
        tags=[str(item) for item in tags],
        style_tokens={str(k): str(v) for k, v in style_tokens.items()},
    )


def _load_all_templates() -> Tuple[PublishedAppAuthTemplate, ...]:
    if not AUTH_TEMPLATE_PACKS_ROOT.exists():
        raise ValueError(f"Auth template packs root not found: {AUTH_TEMPLATE_PACKS_ROOT}")

    templates: List[PublishedAppAuthTemplate] = []
    seen_keys: set[str] = set()
    for path in sorted(AUTH_TEMPLATE_PACKS_ROOT.iterdir()):
        if not path.is_dir():
            continue
        template = _load_manifest(path)
        if template.key in seen_keys:
            raise ValueError(f"Duplicate auth template key found: {template.key}")
        seen_keys.add(template.key)
        templates.append(template)

    if not templates:
        raise ValueError(f"No auth template packs found under: {AUTH_TEMPLATE_PACKS_ROOT}")
    return tuple(templates)


def list_auth_templates() -> List[PublishedAppAuthTemplate]:
    return list(_load_all_templates())


def get_auth_template(auth_template_key: str) -> PublishedAppAuthTemplate:
    for template in _load_all_templates():
        if template.key == auth_template_key:
            return template
    raise KeyError(auth_template_key)
