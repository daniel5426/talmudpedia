#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from e2b import Template


def _is_truthy(raw: str | None, *, default: bool = False) -> bool:
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_env() -> None:
    backend_env = _repo_root() / "backend" / ".env"
    if backend_env.exists():
        load_dotenv(backend_env, override=False)


def _require_env(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable `{name}`.")
    return value


def _build_template() -> dict[str, object]:
    _require_env("E2B_API_KEY")

    alias = (os.getenv("APPS_E2B_TEMPLATE_ALIAS") or "").strip() or "talmudpedia-app-builder-dev"
    primary_tag = (os.getenv("APPS_E2B_TEMPLATE_TAG") or "").strip() or "apps-builder"
    tags_raw = (os.getenv("APPS_E2B_TEMPLATE_TAGS") or "").strip()
    configured_tags = [part.strip() for part in tags_raw.split(",") if part.strip()]
    tags: list[str] = []
    for tag in [primary_tag, *configured_tags, "talmudpedia"]:
        if tag and tag not in tags:
            tags.append(tag)
    cpu_count = max(1, int(os.getenv("APPS_E2B_TEMPLATE_CPU_COUNT", "2")))
    memory_mb = max(512, int(os.getenv("APPS_E2B_TEMPLATE_MEMORY_MB", "2048")))
    skip_cache = _is_truthy(os.getenv("APPS_E2B_TEMPLATE_SKIP_CACHE", "0"), default=False)

    template = Template()
    builder = template.from_template("opencode")

    build = Template.build(
        builder,
        alias,
        alias=alias,
        tags=tags,
        cpu_count=cpu_count,
        memory_mb=memory_mb,
        skip_cache=skip_cache,
    )
    return {
        "alias": alias,
        "template_ref": f"{alias}:{tags[0]}",
        "template_id": getattr(build, "template_id", None),
        "build_id": getattr(build, "build_id", None),
        "cpu_count": cpu_count,
        "memory_mb": memory_mb,
        "tags": list(tags),
    }


def main() -> int:
    _load_env()
    try:
        build = _build_template()
    except Exception as exc:
        print(f"[e2b-template] build failed: {exc}", file=sys.stderr)
        return 1

    print("[e2b-template] build succeeded")
    print(f"alias={build['alias']}")
    print(f"template_ref={build['template_ref']}")
    print(f"template_id={build['template_id']}")
    print(f"build_id={build['build_id']}")
    print(f"cpu_count={build['cpu_count']}")
    print(f"memory_mb={build['memory_mb']}")
    print(f"tags={','.join(build['tags'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
