from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.services.apps_builder_trace import apps_builder_trace_file_path
from app.db.postgres.models.published_apps import PublishedApp
from tests.published_apps._helpers import admin_headers, seed_admin_tenant_and_agent


def _env_truthy(name: str, default: str = "0") -> bool:
    raw = (os.getenv(name) or default).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _live_test_enabled() -> bool:
    return _env_truthy("APPS_BUILDER_LIVE_CODING_E2E")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _report_dir() -> Path:
    root = Path(__file__).resolve().parents[2] / "artifacts" / "e2e" / "apps_builder"
    root.mkdir(parents=True, exist_ok=True)
    return root


class _TimelineReporter:
    def __init__(self, *, label: str):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.base_path = _report_dir() / f"{stamp}-{label}"
        self.events_path = self.base_path.with_suffix(".events.jsonl")
        self.summary_path = self.base_path.with_suffix(".summary.json")
        self.trace_path = self.base_path.with_suffix(".trace.jsonl")
        self._events: list[dict[str, Any]] = []

    def log(self, kind: str, **fields: Any) -> None:
        payload = {"ts": _now_iso(), "kind": kind, **fields}
        self._events.append(payload)
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True, default=str) + "\n")

    def finalize(self, summary: dict[str, Any]) -> None:
        rendered = {
            "generated_at": _now_iso(),
            "events_path": str(self.events_path),
            "trace_path": str(self.trace_path),
            "event_count": len(self._events),
            **summary,
        }
        self.summary_path.write_text(json.dumps(rendered, indent=2, sort_keys=True, default=str), encoding="utf-8")


def _preview_asset_url(preview_url: str, asset_path: str) -> str:
    parsed = urlparse(str(preview_url))
    normalized_asset = str(asset_path or "").strip().lstrip("/")
    base_path = parsed.path
    if normalized_asset:
        base_path = f"{base_path.rstrip('/')}/{normalized_asset}"
    return urlunparse(parsed._replace(path=base_path))


async def _published_app_row(db_session, app_id: str) -> PublishedApp:
    result = await db_session.execute(select(PublishedApp).where(PublishedApp.id == UUID(str(app_id))).limit(1))
    app = result.scalar_one_or_none()
    assert app is not None, app_id
    return app


async def _run_revision_build_now(*, revision_id: str, tenant_id: str, app_id: str, slug: str) -> dict[str, Any]:
    from app.workers.tasks import build_published_app_revision_task

    def _invoke() -> dict[str, Any]:
        result = build_published_app_revision_task.apply(
            kwargs={
                "revision_id": revision_id,
                "tenant_id": tenant_id,
                "app_id": app_id,
                "slug": slug,
                "build_kind": "draft",
            }
        )
        return {
            "successful": result.successful(),
            "failed": result.failed(),
            "result": result.result,
        }

    return await asyncio.to_thread(_invoke)


async def _create_builder_app(client, headers: dict[str, str], agent_id: str, *, name: str) -> str:
    response = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": name,
            "agent_id": agent_id,
            "template_key": "classic-chat",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


async def _ensure_draft_dev_session(
    client,
    app_id: str,
    headers: dict[str, str],
    *,
    reporter: _TimelineReporter | None = None,
) -> dict[str, Any]:
    deadline = asyncio.get_running_loop().time() + float(
        (os.getenv("APPS_BUILDER_LIVE_CODING_SESSION_TIMEOUT_SECONDS") or "180").strip()
    )
    last_payload: dict[str, Any] = {}
    while asyncio.get_running_loop().time() < deadline:
        response = await client.post(f"/admin/apps/{app_id}/builder/draft-dev/session/ensure", headers=headers)
        assert response.status_code == 200, response.text
        payload = response.json()
        last_payload = payload if isinstance(payload, dict) else {"raw": payload}
        if reporter is not None:
            reporter.log(
                "session.ensure",
                status=str(last_payload.get("status") or ""),
                session_id=str(last_payload.get("session_id") or "") or None,
                workspace_status=str(last_payload.get("workspace_status") or "") or None,
                preview_url=str(last_payload.get("preview_url") or "") or None,
            )
        if last_payload.get("status") == "serving":
            assert last_payload.get("preview_url"), last_payload
            assert last_payload.get("preview_auth_token"), last_payload
            return last_payload
        await asyncio.sleep(2.0)
    raise AssertionError(last_payload)


async def _builder_state(client, app_id: str, headers: dict[str, str]) -> dict[str, Any]:
    response = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def _heartbeat_draft_dev_session(client, app_id: str, headers: dict[str, str]) -> None:
    response = await client.post(f"/admin/apps/{app_id}/builder/draft-dev/session/heartbeat", headers=headers)
    assert response.status_code == 200, response.text


async def _versions(client, app_id: str, headers: dict[str, str], *, limit: int = 20) -> list[dict[str, Any]]:
    response = await client.get(f"/admin/apps/{app_id}/versions", headers=headers, params={"limit": limit})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert isinstance(payload, list), payload
    return payload


async def _run_payload(client, app_id: str, run_id: str, headers: dict[str, str]) -> dict[str, Any]:
    response = await client.get(f"/admin/apps/{app_id}/coding-agent/v2/runs/{run_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _maybe_model_id() -> str | None:
    for env_name in ("APPS_BUILDER_LIVE_CODING_MODEL_ID", "OPENCODE_LIVE_MODEL_ID"):
        value = str(os.getenv(env_name) or "").strip()
        if value:
            return value
    return None


async def _submit_prompt(client, app_id: str, headers: dict[str, str], *, prompt: str) -> dict[str, Any]:
    payload: dict[str, Any] = {"input": prompt}
    model_id = _maybe_model_id()
    if model_id:
        payload["model_id"] = model_id
    response = await client.post(f"/admin/apps/{app_id}/coding-agent/v2/prompts", headers=headers, json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["submission_status"] == "started", body
    return body["run"]


def _decode_sse_payload(raw: str) -> dict[str, Any] | None:
    data_lines: list[str] = []
    for line in raw.splitlines():
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
    if not data_lines:
        return None
    joined = "\n".join(data_lines).strip()
    if not joined:
        return None
    try:
        parsed = json.loads(joined)
    except Exception:
        return {"raw": joined}
    return parsed if isinstance(parsed, dict) else {"raw": parsed}


async def _consume_run_stream(
    client,
    *,
    app_id: str,
    run_id: str,
    headers: dict[str, str],
    reporter: _TimelineReporter,
    timeout_seconds: float,
) -> list[dict[str, Any]]:
    url = f"/admin/apps/{app_id}/coding-agent/v2/runs/{run_id}/stream"
    events: list[dict[str, Any]] = []
    async with asyncio.timeout(timeout_seconds):
        async with client.stream("GET", url, headers=headers, timeout=None) as response:
            assert response.status_code == 200, await response.aread()
            buffer: list[str] = []
            async for line in response.aiter_lines():
                if line == "":
                    parsed = _decode_sse_payload("\n".join(buffer))
                    buffer.clear()
                    if parsed is None:
                        continue
                    events.append(parsed)
                    reporter.log(
                        "stream.event",
                        event=str(parsed.get("event") or ""),
                        stage=str(parsed.get("stage") or ""),
                        payload=parsed.get("payload"),
                    )
                    if str(parsed.get("event") or "") in {"run.completed", "run.failed", "run.cancelled", "run.paused"}:
                        break
                    continue
                if line.startswith(":"):
                    reporter.log("stream.heartbeat", raw=line)
                    continue
                buffer.append(line)
    return events


async def _preview_response(client, *, url: str, auth_token: str) -> dict[str, Any]:
    try:
        response = await client.get(
            url,
            params={"runtime_token": auth_token},
            follow_redirects=True,
            timeout=20.0,
        )
        text = response.text if response.status_code == 200 else ""
        return {
            "status_code": response.status_code,
            "contains_marker": False,
            "sha1": hashlib.sha1(text.encode("utf-8")).hexdigest() if text else None,
            "snippet": text[:160] if text else "",
        }
    except Exception as exc:
        return {
            "status_code": None,
            "contains_marker": False,
            "sha1": None,
            "snippet": "",
            "error": f"{exc.__class__.__name__}: {exc}",
        }


async def _preview_source_response(client, *, url: str, auth_token: str, marker: str) -> dict[str, Any]:
    try:
        response = await client.get(
            url,
            params={"runtime_token": auth_token},
            follow_redirects=True,
            timeout=20.0,
        )
        text = response.text if response.status_code == 200 else ""
        return {
            "status_code": response.status_code,
            "contains_marker": marker in text,
            "sha1": hashlib.sha1(text.encode("utf-8")).hexdigest() if text else None,
            "snippet": text[:220] if text else "",
        }
    except Exception as exc:
        return {
            "status_code": None,
            "contains_marker": False,
            "sha1": None,
            "snippet": "",
            "error": f"{exc.__class__.__name__}: {exc}",
        }


async def _latest_version_preview_status(client, app_id: str, version_id: str, headers: dict[str, str]) -> dict[str, Any]:
    try:
        runtime_resp = await client.get(
            f"/admin/apps/{app_id}/versions/{version_id}/preview-runtime",
            headers=headers,
        )
        payload = runtime_resp.json() if runtime_resp.headers.get("content-type", "").startswith("application/json") else {}
        if runtime_resp.status_code != 200:
            return {"preview_runtime_status": runtime_resp.status_code, "asset_status": None, "error": runtime_resp.text[:220]}
        preview_url = str(payload.get("preview_url") or "").strip()
        runtime_token = str(payload.get("runtime_token") or "").strip()
        if not preview_url or not runtime_token:
            return {"preview_runtime_status": 200, "asset_status": None, "error": "preview runtime payload incomplete"}
        asset_resp = await client.get(
            preview_url,
            headers={"Authorization": f"Bearer {runtime_token}"},
            follow_redirects=True,
            timeout=20.0,
        )
        return {
            "preview_runtime_status": runtime_resp.status_code,
            "asset_status": asset_resp.status_code,
            "asset_snippet": asset_resp.text[:160] if asset_resp.status_code == 200 else asset_resp.text[:160],
        }
    except Exception as exc:
        return {
            "preview_runtime_status": None,
            "asset_status": None,
            "error": f"{exc.__class__.__name__}: {exc}",
        }


async def _observe_pipeline(
    client,
    *,
    app_id: str,
    run_id: str,
    headers: dict[str, str],
    preview_url: str,
    preview_auth_token: str,
    marker: str,
    reporter: _TimelineReporter,
    stop_event: asyncio.Event,
    interval_seconds: float = 1.0,
) -> None:
    preview_source_url = _preview_asset_url(preview_url, "src/App.tsx")
    next_heartbeat_at = asyncio.get_running_loop().time()
    while not stop_event.is_set():
        if asyncio.get_running_loop().time() >= next_heartbeat_at:
            await _heartbeat_draft_dev_session(client, app_id, headers)
            reporter.log("session.heartbeat", scope="observer")
            next_heartbeat_at = asyncio.get_running_loop().time() + 20.0
        versions = await _versions(client, app_id, headers, limit=20)
        builder_state = await _builder_state(client, app_id, headers)
        run_payload = await _run_payload(client, app_id, run_id, headers)
        preview_root = await _preview_response(client, url=preview_url, auth_token=preview_auth_token)
        preview_source = await _preview_source_response(
            client,
            url=preview_source_url,
            auth_token=preview_auth_token,
            marker=marker,
        )
        latest_version = versions[0] if versions else {}
        latest_version_id = str(latest_version.get("id") or "") or None
        latest_version_preview = (
            await _latest_version_preview_status(client, app_id, latest_version_id, headers)
            if latest_version_id
            else {"preview_runtime_status": None, "asset_status": None}
        )
        reporter.log(
            "observer.tick",
            run_status=str(run_payload.get("status") or ""),
            result_revision_id=str(run_payload.get("result_revision_id") or "") or None,
            batch_finalized_at=run_payload.get("batch_finalized_at"),
            current_draft_revision_id=(
                builder_state.get("current_draft_revision", {}).get("id")
                if isinstance(builder_state.get("current_draft_revision"), dict)
                else None
            ),
            draft_dev_status=(
                builder_state.get("draft_dev", {}).get("status")
                if isinstance(builder_state.get("draft_dev"), dict)
                else None
            ),
            versions_count=len(versions),
            latest_version_id=latest_version_id,
            latest_version_origin_run_id=str(latest_version.get("origin_run_id") or "") or None,
            latest_version_build_status=str(latest_version.get("build_status") or "") or None,
            preview_root=preview_root,
            preview_source=preview_source,
            latest_version_preview=latest_version_preview,
        )
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            continue


def _filter_trace_lines(*, app_id: str, run_id: str) -> list[str]:
    trace_path = Path(apps_builder_trace_file_path())
    if not trace_path.exists():
        return []
    matches: list[str] = []
    for raw in trace_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if app_id in raw or run_id in raw:
            matches.append(raw)
    return matches


def _find_first_event(events: list[dict[str, Any]], event_name: str) -> dict[str, Any] | None:
    for item in events:
        if item.get("kind") == "observer.tick":
            continue
        if str(item.get("event") or "") == event_name:
            return item
    return None


def _observer_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in events if item.get("kind") == "observer.tick"]


@pytest.mark.asyncio
@pytest.mark.skipif(
    not _live_test_enabled(),
    reason="Set APPS_BUILDER_LIVE_CODING_E2E=1 to run the live App Builder coding-run E2E.",
)
async def test_live_coding_run_updates_preview_and_creates_version(client, db_session, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APPS_SANDBOX_BACKEND", "sprite")
    monkeypatch.setenv("APPS_SANDBOX_CONTROLLER_DEV_SHIM_ENABLED", "0")
    monkeypatch.setenv("APPS_CODING_AGENT_OPENCODE_USE_SANDBOX_CONTROLLER", "0")
    monkeypatch.setenv("APPS_BUILDER_BUILD_AUTOMATION_ENABLED", "1")

    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    marker = f"LIVE-CODING-E2E-{uuid4().hex[:10]}"
    reporter = _TimelineReporter(label=f"coding-run-{marker.lower()}")

    app_id = await _create_builder_app(
        client,
        headers,
        str(agent.id),
        name=f"Live Coding Run E2E {uuid4().hex[:6]}",
    )
    app_row = await _published_app_row(db_session, app_id)
    reporter.log("app.created", app_id=app_id)

    ensure_payload = await _ensure_draft_dev_session(client, app_id, headers, reporter=reporter)
    preview_url = str(ensure_payload["preview_url"])
    preview_auth_token = str(ensure_payload["preview_auth_token"])
    initial_state = await _builder_state(client, app_id, headers)
    initial_revision_id = str(initial_state["current_draft_revision"]["id"])
    initial_versions = await _versions(client, app_id, headers, limit=20)
    initial_version_count = len(initial_versions)
    reporter.log(
        "session.ready",
        session_id=str(ensure_payload["session_id"]),
        preview_url=preview_url,
        initial_revision_id=initial_revision_id,
        initial_version_count=initial_version_count,
    )

    prompt = (
        "Edit `src/App.tsx` in the current app.\n"
        f"Add the exact visible marker text `{marker}` near the top of the main UI so it renders in the app.\n"
        "Use tools to make the edit and verify the file contains that exact marker.\n"
        f"Then reply with exactly: done {marker}"
    )
    run_payload = await _submit_prompt(client, app_id, headers, prompt=prompt)
    run_id = str(run_payload["run_id"])
    reporter.log("run.submitted", run_id=run_id, prompt=prompt, requested_model_id=run_payload.get("requested_model_id"))

    stop_event = asyncio.Event()
    observer_task = asyncio.create_task(
        _observe_pipeline(
            client,
            app_id=app_id,
            run_id=run_id,
            headers=headers,
            preview_url=preview_url,
            preview_auth_token=preview_auth_token,
            marker=marker,
            reporter=reporter,
            stop_event=stop_event,
        )
    )
    stream_events: list[dict[str, Any]] = []
    try:
        stream_events = await _consume_run_stream(
            client,
            app_id=app_id,
            run_id=run_id,
            headers=headers,
            reporter=reporter,
            timeout_seconds=float((os.getenv("APPS_BUILDER_LIVE_CODING_STREAM_TIMEOUT_SECONDS") or "900").strip()),
        )
    finally:
        reporter.log("stream.closed", run_id=run_id, event_count=len(stream_events))

    async def _wait_for_post_run_conditions() -> dict[str, Any]:
        deadline = asyncio.get_running_loop().time() + float(
            (os.getenv("APPS_BUILDER_LIVE_CODING_POST_RUN_TIMEOUT_SECONDS") or "900").strip()
        )
        latest_snapshot: dict[str, Any] = {}
        preview_source_url = _preview_asset_url(preview_url, "src/App.tsx")
        forced_build_revision_id: str | None = None
        next_heartbeat_at = asyncio.get_running_loop().time()
        while asyncio.get_running_loop().time() < deadline:
            if asyncio.get_running_loop().time() >= next_heartbeat_at:
                await _heartbeat_draft_dev_session(client, app_id, headers)
                reporter.log("session.heartbeat", scope="post_run")
                next_heartbeat_at = asyncio.get_running_loop().time() + 20.0
            versions = await _versions(client, app_id, headers, limit=20)
            builder_state = await _builder_state(client, app_id, headers)
            run_state = await _run_payload(client, app_id, run_id, headers)
            preview_source = await _preview_source_response(
                client,
                url=preview_source_url,
                auth_token=preview_auth_token,
                marker=marker,
            )
            latest_version = versions[0] if versions else {}
            latest_version_id = str(latest_version.get("id") or "") or None
            latest_version_preview = (
                await _latest_version_preview_status(client, app_id, latest_version_id, headers)
                if latest_version_id
                else {}
            )
            latest_snapshot = {
                "versions": versions,
                "builder_state": builder_state,
                "run_state": run_state,
                "preview_source": preview_source,
                "latest_version_preview": latest_version_preview,
            }
            if str(run_state.get("status") or "") in {"failed", "cancelled", "paused"}:
                return latest_snapshot
            current_draft_revision_id = (
                builder_state.get("current_draft_revision", {}).get("id")
                if isinstance(builder_state.get("current_draft_revision"), dict)
                else None
            )
            latest_origin_run_id = str(latest_version.get("origin_run_id") or "") or None
            latest_revision_id = str(latest_version.get("id") or "") or None
            latest_build_status = str(latest_version.get("build_status") or "") or None
            build_asset_status = latest_version_preview.get("asset_status")
            if (
                str(run_state.get("status") or "") == "completed"
                and current_draft_revision_id
                and current_draft_revision_id != initial_revision_id
                and len(versions) > initial_version_count
                and latest_origin_run_id == run_id
                and bool(preview_source.get("contains_marker"))
                and latest_build_status == "queued"
                and latest_revision_id
                and forced_build_revision_id is None
            ):
                reporter.log("build.force_start", revision_id=latest_revision_id)
                build_result = await _run_revision_build_now(
                    revision_id=latest_revision_id,
                    tenant_id=str(app_row.tenant_id),
                    app_id=str(app_row.id),
                    slug=str(app_row.slug or ""),
                )
                forced_build_revision_id = latest_revision_id
                reporter.log("build.force_done", revision_id=latest_revision_id, build_result=build_result)
                await asyncio.sleep(1.0)
                continue
            if (
                str(run_state.get("status") or "") == "completed"
                and str(run_state.get("result_revision_id") or "") not in {"", "None"}
                and current_draft_revision_id
                and current_draft_revision_id != initial_revision_id
                and len(versions) > initial_version_count
                and latest_origin_run_id == run_id
                and bool(preview_source.get("contains_marker"))
                and latest_build_status in {"success", "succeeded"}
                and build_asset_status == 200
            ):
                return latest_snapshot
            await asyncio.sleep(2.0)
        return latest_snapshot

    post_run_snapshot = await _wait_for_post_run_conditions()
    stop_event.set()
    await observer_task

    trace_lines = _filter_trace_lines(app_id=app_id, run_id=run_id)
    reporter.trace_path.write_text("\n".join(trace_lines) + ("\n" if trace_lines else ""), encoding="utf-8")

    events = list(reporter._events)
    observer_ticks = _observer_events(events)
    latest_versions = post_run_snapshot.get("versions") if isinstance(post_run_snapshot.get("versions"), list) else []
    latest_version = latest_versions[0] if latest_versions else {}
    latest_build_status = str(latest_version.get("build_status") or "") or None
    current_draft_revision_id = (
        post_run_snapshot.get("builder_state", {}).get("current_draft_revision", {}).get("id")
        if isinstance(post_run_snapshot.get("builder_state"), dict)
        else None
    )
    run_state = post_run_snapshot.get("run_state") if isinstance(post_run_snapshot.get("run_state"), dict) else {}
    preview_source = (
        post_run_snapshot.get("preview_source") if isinstance(post_run_snapshot.get("preview_source"), dict) else {}
    )
    latest_version_preview = (
        post_run_snapshot.get("latest_version_preview")
        if isinstance(post_run_snapshot.get("latest_version_preview"), dict)
        else {}
    )

    reporter.finalize(
        {
            "app_id": app_id,
            "run_id": run_id,
            "marker": marker,
            "initial_revision_id": initial_revision_id,
            "current_draft_revision_id": current_draft_revision_id,
            "initial_version_count": initial_version_count,
            "final_version_count": len(latest_versions),
            "latest_version_id": latest_version.get("id"),
            "latest_version_origin_run_id": latest_version.get("origin_run_id"),
            "latest_version_build_status": latest_build_status,
            "run_status": run_state.get("status"),
            "run_result_revision_id": run_state.get("result_revision_id"),
            "preview_contains_marker": bool(preview_source.get("contains_marker")),
            "latest_version_preview_asset_status": latest_version_preview.get("asset_status"),
            "observer_tick_count": len(observer_ticks),
            "stream_event_count": len(stream_events),
        }
    )

    assert stream_events, f"No stream events captured. See {reporter.summary_path}"
    terminal_events = [item for item in stream_events if str(item.get("event") or "") in {"run.completed", "run.failed", "run.cancelled", "run.paused"}]
    assert terminal_events, f"No terminal stream event captured. See {reporter.summary_path}"
    assert str(terminal_events[-1].get("event") or "") == "run.completed", (
        f"Run did not complete successfully. See {reporter.summary_path}"
    )
    assert str(run_state.get("status") or "") == "completed", f"Run status never settled to completed. See {reporter.summary_path}"
    assert str(run_state.get("result_revision_id") or "").strip(), (
        f"Run completed without result revision. See {reporter.summary_path}"
    )
    assert current_draft_revision_id and current_draft_revision_id != initial_revision_id, (
        f"Draft revision did not advance after coding run. See {reporter.summary_path}"
    )
    assert len(latest_versions) > initial_version_count, f"No new version created after run. See {reporter.summary_path}"
    assert str(latest_version.get("origin_run_id") or "") == run_id, (
        f"Newest version is not linked to the coding run. See {reporter.summary_path}"
    )
    assert bool(preview_source.get("contains_marker")), (
        f"Draft-dev preview source never showed the marker before publish. See {reporter.summary_path}"
    )
    assert latest_build_status in {"success", "succeeded"}, (
        f"Auto-created revision build did not succeed. See {reporter.summary_path}"
    )
    assert latest_version_preview.get("asset_status") == 200, (
        f"Built revision preview asset was not reachable. See {reporter.summary_path}"
    )

    delete_resp = await client.delete(f"/admin/apps/{app_id}", headers=headers)
    assert delete_resp.status_code == 200, delete_resp.text

    with suppress(Exception):
        reporter.log("app.deleted", app_id=app_id)
