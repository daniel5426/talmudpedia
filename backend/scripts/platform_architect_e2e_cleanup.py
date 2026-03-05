#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from typing import Any

from talmudpedia_control_sdk import ControlPlaneClient


def _unwrap(payload: Any) -> dict:
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        return payload["data"]
    if isinstance(payload, dict):
        return payload
    return {}


def _iter_prefixed(items: list[dict], field: str, prefix: str) -> list[dict]:
    out = []
    for item in items:
        value = str(item.get(field, ""))
        if value.startswith(prefix):
            out.append(item)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Cleanup platform architect E2E resources by prefix")
    parser.add_argument("--prefix", default=os.getenv("ARCH_E2E_RESOURCE_PREFIX", "arch-e2e"))
    parser.add_argument("--base-url", default=os.getenv("TEST_BASE_URL", "http://localhost:8000"))
    parser.add_argument("--token", default=os.getenv("TEST_API_KEY"))
    parser.add_argument("--tenant-id", default=os.getenv("TEST_TENANT_ID"))
    parser.add_argument("--tenant-slug", default=os.getenv("TEST_TENANT_SLUG"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()

    if not args.token or not args.tenant_id:
        raise SystemExit("Missing TEST_API_KEY or TEST_TENANT_ID")

    if not args.dry_run and not args.confirm:
        raise SystemExit("Refusing to mutate without --confirm (or use --dry-run)")

    client = ControlPlaneClient(base_url=args.base_url.rstrip("/"), token=args.token, tenant_id=args.tenant_id)
    summary: dict[str, int] = {}

    def _mark(name: str, n: int = 1):
        summary[name] = summary.get(name, 0) + n

    agents = _unwrap(client.agents.list(limit=500)).get("agents", [])
    target_agents = _iter_prefixed(agents, "slug", args.prefix)
    for agent in target_agents:
        _mark("agents_found")
        if args.confirm and not args.dry_run:
            try:
                client.agents.delete(str(agent["id"]))
                _mark("agents_deleted")
            except Exception:
                _mark("agents_delete_failed")

    pipelines: list[dict] = []
    if args.tenant_slug:
        pipelines = _unwrap(client.rag.list_visual_pipelines(tenant_slug=args.tenant_slug)).get("data", [])
    target_pipelines = _iter_prefixed(pipelines, "slug", args.prefix)
    for pipeline in target_pipelines:
        _mark("pipelines_found")
        if args.confirm and not args.dry_run:
            try:
                client.rag.delete_visual_pipeline(str(pipeline["id"]), tenant_slug=args.tenant_slug)
                _mark("pipelines_deleted")
            except Exception:
                _mark("pipelines_delete_failed")

    tools = _unwrap(client.tools.list(limit=500)).get("tools", [])
    target_tools = _iter_prefixed(tools, "slug", args.prefix)
    for tool in target_tools:
        _mark("tools_found")
        if args.confirm and not args.dry_run:
            try:
                client.tools.delete(str(tool["id"]))
                _mark("tools_deleted")
            except Exception:
                _mark("tools_delete_failed")

    models = _unwrap(client.models.list(limit=500, is_active=None)).get("models", [])
    target_models = _iter_prefixed(models, "slug", args.prefix)
    for model in target_models:
        _mark("models_found")
        if args.confirm and not args.dry_run:
            try:
                client.models.delete(str(model["id"]))
                _mark("models_deleted")
            except Exception:
                _mark("models_delete_failed")

    if args.tenant_slug:
        artifacts = _unwrap(client.artifacts.list(tenant_slug=args.tenant_slug)).get("data", [])
        target_artifacts = _iter_prefixed(artifacts, "name", args.prefix)
        for artifact in target_artifacts:
            _mark("artifacts_found")
            if args.confirm and not args.dry_run:
                try:
                    client.artifacts.delete(str(artifact["id"]), tenant_slug=args.tenant_slug)
                    _mark("artifacts_deleted")
                except Exception:
                    _mark("artifacts_delete_failed")

        stores = _unwrap(client.knowledge_stores.list(tenant_slug=args.tenant_slug)).get("data", [])
        target_stores = _iter_prefixed(stores, "name", args.prefix)
        for store in target_stores:
            _mark("knowledge_stores_found")
            if args.confirm and not args.dry_run:
                try:
                    client.knowledge_stores.delete(str(store["id"]), tenant_slug=args.tenant_slug)
                    _mark("knowledge_stores_deleted")
                except Exception:
                    _mark("knowledge_stores_delete_failed")

    print("Cleanup summary:")
    for key in sorted(summary.keys()):
        print(f"  {key}: {summary[key]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
