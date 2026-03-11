#!/usr/bin/env python3
"""
End-to-end probe for the current Cloudflare-backed artifact test-run path.

This script creates an unsaved artifact test run through the backend admin API,
polls the resulting run record, and prints the final payload.

It exercises:
- unsaved source-tree test runs
- multi-file artifact loading/imports
- async execute()
- stdlib-heavy logic on the current free-plan Cloudflare runtime
- declared dependency plumbing

Important limitation:
- In the temporary `standard_worker_test` runtime mode, declared dependencies
  are carried through the backend flow but are not dynamically installed per
  artifact execution. This probe therefore uses standard-library imports in the
  artifact source while still declaring a few dependencies for publish-path
  compatibility checks later.

Usage:
    BACKEND_BEARER_TOKEN=... python3 backend/scripts/test_cloudflare_artifact_runtime.py

Optional env:
    BACKEND_BASE_URL=http://127.0.0.1:8000
    TENANT_SLUG=my-tenant
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
POLL_TIMEOUT_SECONDS = 45.0
POLL_INTERVAL_SECONDS = 1.0


HANDLER_CODE = """
from helpers.analysis import build_summary
from helpers.formatting import compact_preview


async def execute(inputs, config, context):
    documents = inputs.get("documents") or []
    user_prompt = inputs.get("prompt") or ""
    summary = build_summary(documents=documents, prompt=user_prompt, config=config, context=context)
    return {
        "ok": True,
        "summary": summary,
        "preview": compact_preview(documents),
        "meta": {
            "tenant_id": context.get("tenant_id"),
            "domain": context.get("domain"),
            "revision_id": context.get("revision_id"),
            "declared_mode": config.get("mode", "demo"),
        },
    }
"""


ANALYSIS_CODE = """
import hashlib
import json
import statistics
from collections import Counter
from datetime import datetime, timezone
from difflib import SequenceMatcher
from urllib.parse import urlparse


def _tokenize(text):
    return [part.strip(".,!?;:\\\"'()[]{}").lower() for part in text.split() if part.strip()]


def build_summary(*, documents, prompt, config, context):
    texts = [str(item.get("text") or "") for item in documents if isinstance(item, dict)]
    combined = "\\n".join(texts)
    tokens = _tokenize(combined)
    token_counts = Counter(tokens)
    lengths = [len(text) for text in texts] or [0]
    prompt_similarity = SequenceMatcher(None, combined[:400], str(prompt)[:400]).ratio() if prompt else 0.0

    sources = []
    for item in documents:
        if not isinstance(item, dict):
            continue
        raw_url = str(item.get("url") or "")
        if not raw_url:
            continue
        parsed = urlparse(raw_url)
        sources.append(parsed.netloc or raw_url)

    digest = hashlib.sha256(
        json.dumps(
            {
                "documents": documents,
                "prompt": prompt,
                "mode": config.get("mode"),
                "tenant_id": context.get("tenant_id"),
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()

    return {
        "document_count": len(texts),
        "char_count": len(combined),
        "avg_document_length": round(statistics.mean(lengths), 2),
        "median_document_length": round(statistics.median(lengths), 2),
        "top_tokens": token_counts.most_common(8),
        "source_hosts": sorted(set(sources)),
        "prompt_similarity": round(prompt_similarity, 4),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "digest": digest,
    }
"""


FORMATTING_CODE = """
def compact_preview(documents):
    preview = []
    for item in documents[:3]:
        if not isinstance(item, dict):
            preview.append({"kind": "unknown", "value": str(item)[:80]})
            continue
        preview.append(
            {
                "title": str(item.get("title") or "")[:40],
                "text_preview": str(item.get("text") or "")[:120],
                "url": item.get("url"),
            }
        )
    return preview
"""


SOURCE_FILES = [
    {"path": "handler.py", "content": HANDLER_CODE.strip() + "\n"},
    {"path": "helpers/__init__.py", "content": ""},
    {"path": "helpers/analysis.py", "content": ANALYSIS_CODE.strip() + "\n"},
    {"path": "helpers/formatting.py", "content": FORMATTING_CODE.strip() + "\n"},
]


TEST_REQUEST = {
    "source_files": SOURCE_FILES,
    "entry_module_path": "handler.py",
    "input_data": {
        "prompt": "Summarize the shared themes across these notes.",
        "documents": [
            {
                "title": "Note A",
                "text": "The sugya discusses disagreement, obligation, and practical application in Beit Din.",
                "url": "https://example.org/a",
            },
            {
                "title": "Note B",
                "text": "A second note focuses on obligation, dispute resolution, and the structure of the argument.",
                "url": "https://example.org/b",
            },
            {
                "title": "Note C",
                "text": "This note adds practical consequences and a narrower distinction in the reasoning.",
                "url": "https://example.org/c",
            },
        ],
    },
    "config": {
        "mode": "cloudflare_probe",
        "include_debug_fields": True,
    },
    "dependencies": [
        "pydantic>=2,<3",
        "python-dateutil>=2.9,<3",
        "httpx>=0.27,<1",
    ],
    "input_type": "raw_documents",
    "output_type": "json",
}


def _http_json(method: str, url: str, *, token: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed with {exc.code}: {detail}") from exc


def _build_url(base_url: str, path: str, *, tenant_slug: str | None = None) -> str:
    url = base_url.rstrip("/") + path
    if tenant_slug:
        return url + "?" + urllib.parse.urlencode({"tenant_slug": tenant_slug})
    return url


def main() -> int:
    base_url = os.getenv("BACKEND_BASE_URL", DEFAULT_BASE_URL).strip()
    token = os.getenv("BACKEND_BEARER_TOKEN", "").strip()
    tenant_slug = os.getenv("TENANT_SLUG", "").strip() or None
    if not token:
        print("BACKEND_BEARER_TOKEN is required", file=sys.stderr)
        return 2

    create_url = _build_url(base_url, "/admin/artifacts/test-runs", tenant_slug=tenant_slug)
    print(f"Creating test run via {create_url}")
    created = _http_json("POST", create_url, token=token, payload=TEST_REQUEST)
    run_id = str(created.get("run_id") or "")
    if not run_id:
        print(json.dumps(created, indent=2), file=sys.stderr)
        raise RuntimeError("run_id missing from create response")
    print(f"Created run_id={run_id}")

    status_url = _build_url(base_url, f"/admin/artifact-runs/{run_id}", tenant_slug=tenant_slug)
    events_url = _build_url(base_url, f"/admin/artifact-runs/{run_id}/events", tenant_slug=tenant_slug)
    deadline = time.time() + POLL_TIMEOUT_SECONDS

    while time.time() < deadline:
        payload = _http_json("GET", status_url, token=token)
        status = str(payload.get("status") or "")
        print(f"status={status}")
        if status in {"completed", "failed", "cancelled"}:
            print("\nFinal run payload:")
            print(json.dumps(payload, indent=2, sort_keys=True))
            print("\nRun events:")
            print(json.dumps(_http_json("GET", events_url, token=token), indent=2, sort_keys=True))
            return 0 if status == "completed" else 1
        time.sleep(POLL_INTERVAL_SECONDS)

    print(f"Timed out waiting for run {run_id}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
