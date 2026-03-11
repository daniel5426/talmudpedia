from __future__ import annotations

import json
import os
from typing import Any

import httpx


class CloudflareArtifactRuntimeError(RuntimeError):
    pass


class CloudflareArtifactClient:
    def __init__(self) -> None:
        self._api_base = (os.getenv("CLOUDFLARE_API_BASE_URL") or "https://api.cloudflare.com/client/v4").rstrip("/")
        self._account_id = str(os.getenv("CLOUDFLARE_ACCOUNT_ID") or "").strip()
        self._api_token = str(os.getenv("CLOUDFLARE_API_TOKEN") or "").strip()

    async def deploy_worker(
        self,
        *,
        script_name: str,
        modules: list[dict[str, Any]],
        metadata: dict[str, Any],
        namespace: str,
    ) -> dict[str, Any]:
        self._require_config()
        url = f"{self._api_base}/accounts/{self._account_id}/workers/scripts/{script_name}"
        form_parts = {
            "metadata": (
                None,
                json.dumps(
                    {
                        "main_module": "main.py",
                        "compatibility_date": os.getenv("CLOUDFLARE_WORKERS_COMPATIBILITY_DATE", "2026-03-11"),
                        "bindings": [],
                        "dispatch_namespace": namespace,
                        "annotations": metadata,
                    }
                ),
                "application/json",
            )
        }
        for index, module in enumerate(modules):
            content = module.get("content")
            if isinstance(content, dict):
                content = json.dumps(content)
            form_parts[f"module_{index}"] = (
                str(module.get("name") or f"module_{index}"),
                str(content or ""),
                "application/python" if module.get("type") == "python" else "application/json",
            )
        async with httpx.AsyncClient(timeout=float(os.getenv("CLOUDFLARE_API_TIMEOUT_SECONDS") or "60")) as client:
            response = await client.put(
                url,
                headers={"Authorization": f"Bearer {self._api_token}"},
                files=form_parts,
            )
        response.raise_for_status()
        payload = response.json()
        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, dict):
            raise CloudflareArtifactRuntimeError("Cloudflare deploy response is invalid")
        return result

    def _require_config(self) -> None:
        if not self._account_id:
            raise CloudflareArtifactRuntimeError("CLOUDFLARE_ACCOUNT_ID is required")
        if not self._api_token:
            raise CloudflareArtifactRuntimeError("CLOUDFLARE_API_TOKEN is required")
