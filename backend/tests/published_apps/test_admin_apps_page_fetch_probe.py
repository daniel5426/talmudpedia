import asyncio
from dataclasses import dataclass
from time import perf_counter

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.db.postgres.models.agents import Agent, AgentStatus
from app.db.postgres.models.identity import MembershipStatus, OrgMembership

from ._helpers import admin_headers, seed_admin_tenant_and_agent


@dataclass
class TimedFetch:
    path: str
    elapsed_ms: float
    status_code: int
    item_count: int | None
    total_count: int | None


async def _timed_get(client, path: str, headers: dict[str, str]) -> TimedFetch:
    started_at = perf_counter()
    response = await client.get(path, headers=headers)
    elapsed_ms = (perf_counter() - started_at) * 1000

    payload = response.json()
    item_count: int | None = None
    total_count: int | None = None
    if isinstance(payload, list):
        item_count = len(payload)
    elif isinstance(payload, dict):
        if isinstance(payload.get("agents"), list):
            item_count = len(payload["agents"])
        total = payload.get("total")
        if isinstance(total, int):
            total_count = total

    return TimedFetch(
        path=path,
        elapsed_ms=elapsed_ms,
        status_code=response.status_code,
        item_count=item_count,
        total_count=total_count,
    )


async def _new_app_client() -> AsyncClient:
    from main import app

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _print_probe_summary(title: str, results: list[TimedFetch]) -> None:
    print(f"\n{title}")
    for result in results:
        extras: list[str] = []
        if result.item_count is not None:
            extras.append(f"items={result.item_count}")
        if result.total_count is not None:
            extras.append(f"total={result.total_count}")
        extra_suffix = f" ({', '.join(extras)})" if extras else ""
        print(
            f"  {result.path}: {result.elapsed_ms:.1f}ms status={result.status_code}{extra_suffix}"
        )


async def _run_apps_page_probe(client, headers: dict[str, str]) -> tuple[list[TimedFetch], list[TimedFetch], float]:
    paths = [
        "/admin/apps",
        "/agents?limit=500&compact=true",
        "/admin/apps/templates",
        "/admin/apps/auth/templates",
    ]

    sequential_results = [await _timed_get(client, path, headers) for path in paths]

    async def _parallel_fetch(path: str) -> TimedFetch:
        async with await _new_app_client() as parallel_client:
            return await _timed_get(parallel_client, path, headers)

    started_at = perf_counter()
    parallel_results = await asyncio.gather(*[_parallel_fetch(path) for path in paths])
    parallel_elapsed_ms = (perf_counter() - started_at) * 1000

    return sequential_results, list(parallel_results), parallel_elapsed_ms


@pytest.mark.asyncio
async def test_apps_page_fetch_probe_smoke(db_session):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))

    db_session.add_all(
        [
            Agent(
                tenant_id=tenant.id,
                name=f"Draft Agent {index}",
                slug=f"draft-agent-{index}",
                status=AgentStatus.draft,
                graph_definition={"nodes": [], "edges": []},
                created_by=user.id,
            )
            for index in range(3)
        ]
    )
    await db_session.flush()

    async with await _new_app_client() as client:
        create_response = await client.post(
            "/admin/apps",
            headers=headers,
            json={
                "name": "Probe App",
                "slug": "probe-app",
                "agent_id": str(agent.id),
                "template_key": "classic-chat",
                "auth_enabled": True,
                "auth_providers": ["password"],
            },
        )
        assert create_response.status_code == 200

        sequential_results, parallel_results, parallel_elapsed_ms = await _run_apps_page_probe(
            client, headers
        )

    for result in sequential_results + parallel_results:
        assert result.status_code == 200

    apps_result = next(result for result in sequential_results if result.path == "/admin/apps")
    agents_result = next(
        result for result in sequential_results if result.path == "/agents?limit=500&compact=true"
    )
    assert apps_result.item_count is not None and apps_result.item_count >= 1
    assert agents_result.item_count is not None and agents_result.item_count >= 1
    assert parallel_elapsed_ms >= 0


@pytest.mark.asyncio
@pytest.mark.real_db
async def test_apps_page_fetch_probe_real_db(
    db_session,
    test_tenant_id,
    test_user_id,
):
    membership = await db_session.scalar(
        select(OrgMembership).where(
            OrgMembership.user_id == test_user_id,
            OrgMembership.tenant_id == test_tenant_id,
            OrgMembership.status == MembershipStatus.active,
        )
    )
    assert membership is not None, "Active membership is required for the real DB probe"

    headers = admin_headers(
        str(test_user_id),
        str(test_tenant_id),
        str(membership.org_unit_id),
    )

    async with await _new_app_client() as client:
        sequential_results, parallel_results, parallel_elapsed_ms = await _run_apps_page_probe(
            client, headers
        )

    for result in sequential_results + parallel_results:
        assert result.status_code == 200

    _print_probe_summary("Apps Page Probe Sequential", sequential_results)
    _print_probe_summary("Apps Page Probe Parallel", parallel_results)

    slowest_parallel = max(parallel_results, key=lambda result: result.elapsed_ms)
    print(
        f"\nApps page parallel total: {parallel_elapsed_ms:.1f}ms; "
        f"slowest endpoint: {slowest_parallel.path} ({slowest_parallel.elapsed_ms:.1f}ms)"
    )
