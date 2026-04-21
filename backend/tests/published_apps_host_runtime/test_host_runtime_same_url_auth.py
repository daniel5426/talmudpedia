import jwt
import pytest
from sqlalchemy import func, select
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from app.core.security import ALGORITHM, SECRET_KEY
from app.db.postgres.models.agent_threads import AgentThread, AgentThreadSurface, AgentThreadTurnStatus
from app.db.postgres.models.agents import AgentRun
from app.db.postgres.models.identity import User
from app.db.postgres.models.published_apps import PublishedAppAccount, PublishedAppRevision, PublishedAppRevisionKind
from app.services.security_bootstrap_service import SecurityBootstrapService
from app.services.thread_service import ThreadService
from tests.published_apps._helpers import install_stub_agent_worker, seed_admin_tenant_and_agent, seed_published_app


def _host_headers(slug: str) -> dict[str, str]:
    return {"Host": f"{slug}.apps.localhost"}


def _host_headers_with_cookie(slug: str, token: str) -> dict[str, str]:
    headers = _host_headers(slug)
    headers["Cookie"] = f"published_app_session={token}"
    return headers


def _token_with_scopes(token: str, scopes: list[str]) -> str:
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    payload["scope"] = scopes
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


@pytest.mark.asyncio
async def test_host_root_renders_same_url_auth_shell(client, db_session):
    tenant, owner, _, agent = await seed_admin_tenant_and_agent(db_session)
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        owner.id,
        slug="same-url-auth-app",
        auth_enabled=True,
        auth_providers=["password"],
        description="Sign in to use this app",
        auth_template_key="auth-split",
    )

    resp = await client.get("/", headers=_host_headers(app.public_id))
    assert resp.status_code == 200
    assert app.name in resp.text
    assert "Sign in to use this app" in resp.text
    assert "/_talmudpedia/auth/login" in resp.text


@pytest.mark.asyncio
async def test_host_signup_sets_cookie_and_auth_state(client, db_session):
    tenant, owner, _, agent = await seed_admin_tenant_and_agent(db_session)
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        owner.id,
        slug="same-url-signup-app",
        auth_enabled=True,
        auth_providers=["password"],
    )

    signup_resp = await client.post(
        "/_talmudpedia/auth/signup",
        headers=_host_headers(app.public_id),
        json={"email": "same-url-user@example.com", "password": "secret123"},
    )
    assert signup_resp.status_code == 200
    assert signup_resp.json()["status"] == "ok"
    assert "published_app_session=" in signup_resp.headers.get("set-cookie", "")

    state_resp = await client.get("/_talmudpedia/auth/state", headers=_host_headers(app.public_id))
    assert state_resp.status_code == 200
    payload = state_resp.json()
    assert payload["authenticated"] is True
    assert payload["app"]["public_id"] == app.public_id
    assert payload["user"]["email"] == "same-url-user@example.com"


@pytest.mark.asyncio
async def test_host_same_email_across_apps_creates_distinct_app_accounts(client, db_session):
    tenant, owner, _, agent = await seed_admin_tenant_and_agent(db_session)
    app_a = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        owner.id,
        slug="same-email-app-a",
        auth_enabled=True,
        auth_providers=["password"],
    )
    app_b = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        owner.id,
        slug="same-email-app-b",
        auth_enabled=True,
        auth_providers=["password"],
    )

    email = "shared-human@example.com"
    resp_a = await client.post(
        "/_talmudpedia/auth/signup",
        headers=_host_headers(app_a.public_id),
        json={"email": email, "password": "secret123"},
    )
    assert resp_a.status_code == 200

    await client.post("/_talmudpedia/auth/logout", headers=_host_headers(app_a.public_id))

    resp_b = await client.post(
        "/_talmudpedia/auth/signup",
        headers=_host_headers(app_b.public_id),
        json={"email": email, "password": "secret123"},
    )
    assert resp_b.status_code == 200

    accounts = (
        await db_session.execute(
            select(PublishedAppAccount)
            .where(
                PublishedAppAccount.email == email,
                PublishedAppAccount.published_app_id.in_([app_a.id, app_b.id]),
            )
            .order_by(PublishedAppAccount.published_app_id)
        )
    ).scalars().all()
    assert len(accounts) == 2
    assert str(accounts[0].id) != str(accounts[1].id)
    assert str(accounts[0].published_app_id) != str(accounts[1].published_app_id)
    assert accounts[0].global_user_id is not None
    assert accounts[0].global_user_id == accounts[1].global_user_id


@pytest.mark.asyncio
async def test_host_chat_stream_requires_cookie_when_auth_enabled(client, db_session):
    tenant, owner, _, agent = await seed_admin_tenant_and_agent(db_session)
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        owner.id,
        slug="same-url-chat-auth-required",
        auth_enabled=True,
        auth_providers=["password"],
    )

    resp = await client.post(
        "/_talmudpedia/chat/stream",
        headers=_host_headers(app.public_id),
        json={"input": "hello"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Authentication required"


@pytest.mark.asyncio
async def test_host_chat_stream_uses_cookie_auth_and_persists(client, db_session, monkeypatch):
    tenant, owner, _, agent = await seed_admin_tenant_and_agent(db_session)
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        owner.id,
        slug="same-url-chat-app",
        auth_enabled=True,
        auth_providers=["password"],
    )

    signup_resp = await client.post(
        "/_talmudpedia/auth/signup",
        headers=_host_headers(app.public_id),
        json={"email": "chat-cookie-user@example.com", "password": "secret123"},
    )
    assert signup_resp.status_code == 200
    signup_user = (
        await db_session.execute(
            select(User).where(User.email == "chat-cookie-user@example.com")
        )
    ).scalar_one()
    bootstrap = SecurityBootstrapService(db_session)
    await bootstrap.ensure_default_roles(tenant.id)
    await bootstrap.ensure_organization_reader_assignment(
        organization_id=tenant.id,
        user_id=signup_user.id,
        assigned_by=owner.id,
    )
    await db_session.commit()

    install_stub_agent_worker(monkeypatch, content="Hello from host runtime")

    stream_resp = await client.post(
        "/_talmudpedia/chat/stream",
        headers=_host_headers(app.public_id),
        json={"input": "Hi there"},
    )
    assert stream_resp.status_code == 200, stream_resp.text
    assert "Hello from host runtime" in stream_resp.text
    assert stream_resp.headers.get("X-Thread-ID")

    thread_count = await db_session.scalar(
        select(func.count(AgentThread.id)).where(AgentThread.published_app_id == app.id)
    )
    assert thread_count == 1


@pytest.mark.asyncio
async def test_host_thread_detail_is_scoped_to_app_account(client, db_session, monkeypatch):
    tenant, owner, _, agent = await seed_admin_tenant_and_agent(db_session)
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        owner.id,
        slug="thread-scope-app",
        auth_enabled=True,
        auth_providers=["password"],
    )

    signup_resp = await client.post(
        "/_talmudpedia/auth/signup",
        headers=_host_headers(app.public_id),
        json={"email": "owner-one@example.com", "password": "secret123"},
    )
    assert signup_resp.status_code == 200
    signup_user = (
        await db_session.execute(
            select(User).where(User.email == "owner-one@example.com")
        )
    ).scalar_one()
    bootstrap = SecurityBootstrapService(db_session)
    await bootstrap.ensure_default_roles(tenant.id)
    await bootstrap.ensure_organization_reader_assignment(
        organization_id=tenant.id,
        user_id=signup_user.id,
        assigned_by=owner.id,
    )
    await db_session.commit()

    install_stub_agent_worker(monkeypatch, content="Thread scoped response")

    stream_resp = await client.post(
        "/_talmudpedia/chat/stream",
        headers=_host_headers(app.public_id),
        json={"input": "private thread"},
    )
    assert stream_resp.status_code == 200
    thread_id = stream_resp.headers.get("X-Thread-ID")
    assert thread_id

    await client.post("/_talmudpedia/auth/logout", headers=_host_headers(app.public_id))

    second_signup = await client.post(
        "/_talmudpedia/auth/signup",
        headers=_host_headers(app.public_id),
        json={"email": "owner-two@example.com", "password": "secret123"},
    )
    assert second_signup.status_code == 200

    thread_resp = await client.get(
        f"/_talmudpedia/threads/{thread_id}",
        headers=_host_headers(app.public_id),
    )
    assert thread_resp.status_code == 404


@pytest.mark.asyncio
async def test_host_runtime_rejects_cross_app_cookie_replay(client, db_session):
    tenant, owner, _, agent = await seed_admin_tenant_and_agent(db_session)
    app_a = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        owner.id,
        slug="host-replay-app-a",
        auth_enabled=True,
        auth_providers=["password"],
    )
    app_b = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        owner.id,
        slug="host-replay-app-b",
        auth_enabled=True,
        auth_providers=["password"],
    )

    signup_resp = await client.post(
        "/_talmudpedia/auth/signup",
        headers=_host_headers(app_a.public_id),
        json={"email": "host-replay@example.com", "password": "secret123"},
    )
    token = signup_resp.headers["set-cookie"].split("published_app_session=", 1)[1].split(";", 1)[0]

    replay_resp = await client.post(
        "/_talmudpedia/chat/stream",
        headers=_host_headers_with_cookie(app_b.public_id, token),
        json={"input": "hello"},
    )
    assert replay_resp.status_code == 401
    assert replay_resp.json()["detail"] == "Authentication required"


@pytest.mark.asyncio
async def test_host_runtime_enforces_published_app_scopes(client, db_session):
    tenant, owner, _, agent = await seed_admin_tenant_and_agent(db_session)
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        owner.id,
        slug="host-scope-app",
        auth_enabled=True,
        auth_providers=["password"],
    )

    signup_resp = await client.post(
        "/_talmudpedia/auth/signup",
        headers=_host_headers(app.public_id),
        json={"email": "host-scoped@example.com", "password": "secret123"},
    )
    token = signup_resp.headers["set-cookie"].split("published_app_session=", 1)[1].split(";", 1)[0]

    chat_resp = await client.post(
        "/_talmudpedia/chat/stream",
        headers=_host_headers_with_cookie(app.public_id, _token_with_scopes(token, ["public.auth", "public.chats.read"])),
        json={"input": "hello"},
    )
    assert chat_resp.status_code == 403
    assert chat_resp.json()["detail"] == "Missing required scopes: public.chat"

    threads_resp = await client.get(
        "/_talmudpedia/threads",
        headers=_host_headers_with_cookie(app.public_id, _token_with_scopes(token, ["public.auth", "public.chat"])),
    )
    assert threads_resp.status_code == 403
    assert threads_resp.json()["detail"] == "Missing required scopes: public.chats.read"


@pytest.mark.asyncio
async def test_host_thread_detail_includes_public_run_events(client, db_session, monkeypatch):
    tenant, owner, _, agent = await seed_admin_tenant_and_agent(db_session)
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        owner.id,
        slug="thread-history-events-app",
        auth_enabled=True,
        auth_providers=["password"],
    )

    signup_resp = await client.post(
        "/_talmudpedia/auth/signup",
        headers=_host_headers(app.public_id),
        json={"email": "history-events@example.com", "password": "secret123"},
    )
    assert signup_resp.status_code == 200
    signup_user = (
        await db_session.execute(select(User).where(User.email == "history-events@example.com"))
    ).scalar_one()
    bootstrap = SecurityBootstrapService(db_session)
    await bootstrap.ensure_default_roles(tenant.id)
    await bootstrap.ensure_organization_reader_assignment(
        organization_id=tenant.id,
        user_id=signup_user.id,
        assigned_by=owner.id,
    )
    await db_session.commit()

    async def fake_list_public_run_events(*, db, run_id, view, after_sequence=None, limit=None):
        _ = db, view, after_sequence, limit
        return [
            {
                "version": "run-stream.v2",
                "seq": 1,
                "ts": "2026-03-22T00:00:00Z",
                "event": "reasoning.update",
                "run_id": str(run_id),
                "stage": "assistant",
                "payload": {"content": "Checking context"},
                "diagnostics": [],
            }
        ]

    monkeypatch.setattr(
        "app.services.runtime_surface.service.list_run_events",
        fake_list_public_run_events,
    )

    app_account = (
        await db_session.execute(
            select(PublishedAppAccount).where(
                PublishedAppAccount.published_app_id == app.id,
                PublishedAppAccount.email == "history-events@example.com",
            )
        )
    ).scalar_one()

    thread_service = ThreadService(db_session)
    resolved = await thread_service.resolve_or_create_thread(
        organization_id=tenant.id,
        project_id=app.project_id,
        user_id=None,
        app_account_id=app_account.id,
        agent_id=agent.id,
        published_app_id=app.id,
        surface=AgentThreadSurface.published_host_runtime,
        thread_id=None,
        input_text="hydrate this thread",
    )
    run = AgentRun(
        organization_id=tenant.id,
        project_id=app.project_id,
        agent_id=agent.id,
        initiator_user_id=owner.id,
        thread_id=resolved.thread.id,
        input_params={"input": "hydrate this thread"},
    )
    db_session.add(run)
    await db_session.flush()
    await thread_service.start_turn(
        thread_id=resolved.thread.id,
        run_id=run.id,
        user_input_text="hydrate this thread",
    )
    await thread_service.complete_turn(
        run_id=run.id,
        status=AgentThreadTurnStatus.completed,
        assistant_output_text="History response",
        metadata={
            "final_output": "History response",
            "response_blocks": [
                {
                    "id": f"assistant-text:{run.id}:1",
                    "kind": "assistant_text",
                    "runId": str(run.id),
                    "seq": 1,
                    "status": "complete",
                    "text": "History response",
                    "ts": None,
                    "source": {"event": "assistant.text", "stage": "assistant"},
                }
            ],
        },
    )
    await db_session.commit()

    thread_resp = await client.get(
        f"/_talmudpedia/threads/{resolved.thread.id}",
        headers=_host_headers(app.public_id),
    )
    assert thread_resp.status_code == 200
    payload = thread_resp.json()
    assert len(payload["turns"]) == 1
    assert payload["turns"][0]["response_blocks"] == [
        {
            "id": f"assistant-text:{run.id}:1",
            "kind": "assistant_text",
            "runId": str(run.id),
            "seq": 1,
            "status": "complete",
            "text": "History response",
            "ts": None,
            "source": {"event": "assistant.text", "stage": "assistant"},
        }
    ]
    assert payload["turns"][0]["run_events"][0]["event"] == "reasoning.update"


@pytest.mark.asyncio
async def test_host_thread_detail_returns_subthread_tree_when_requested(client, db_session):
    tenant, owner, _, agent = await seed_admin_tenant_and_agent(db_session)
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        owner.id,
        slug="host-subthreads-app",
        auth_enabled=True,
        auth_providers=["password"],
    )

    signup_resp = await client.post(
        "/_talmudpedia/auth/signup",
        headers=_host_headers(app.public_id),
        json={"email": "subthreads-host@example.com", "password": "secret123"},
    )
    assert signup_resp.status_code == 200
    signup_user = (
        await db_session.execute(select(User).where(User.email == "subthreads-host@example.com"))
    ).scalar_one()
    bootstrap = SecurityBootstrapService(db_session)
    await bootstrap.ensure_default_roles(tenant.id)
    await bootstrap.ensure_organization_reader_assignment(
        organization_id=tenant.id,
        user_id=signup_user.id,
        assigned_by=owner.id,
    )
    await db_session.commit()

    app_account = (
        await db_session.execute(
            select(PublishedAppAccount).where(
                PublishedAppAccount.published_app_id == app.id,
                PublishedAppAccount.email == "subthreads-host@example.com",
            )
        )
    ).scalar_one()

    thread_service = ThreadService(db_session)
    resolved = await thread_service.resolve_or_create_thread(
        organization_id=tenant.id,
        project_id=app.project_id,
        user_id=None,
        app_account_id=app_account.id,
        agent_id=agent.id,
        published_app_id=app.id,
        surface=AgentThreadSurface.published_host_runtime,
        thread_id=None,
        input_text="root thread",
    )
    run = AgentRun(
        organization_id=tenant.id,
        project_id=app.project_id,
        agent_id=agent.id,
        initiator_user_id=owner.id,
        published_app_id=app.id,
        published_app_account_id=app_account.id,
        thread_id=resolved.thread.id,
        input_params={"input": "root thread"},
    )
    db_session.add(run)
    await db_session.flush()
    root_turn = await thread_service.start_turn(
        thread_id=resolved.thread.id,
        run_id=run.id,
        user_input_text="root thread",
    )

    child_thread = AgentThread(
        organization_id=tenant.id,
        project_id=app.project_id,
        app_account_id=app_account.id,
        agent_id=agent.id,
        published_app_id=app.id,
        surface=AgentThreadSurface.published_host_runtime,
        title="Host child thread",
        root_thread_id=resolved.thread.id,
        parent_thread_id=resolved.thread.id,
        parent_thread_turn_id=root_turn.id,
        spawned_by_run_id=run.id,
        lineage_depth=1,
    )
    db_session.add(child_thread)
    await db_session.flush()
    child_run = AgentRun(
        organization_id=tenant.id,
        project_id=app.project_id,
        agent_id=agent.id,
        initiator_user_id=owner.id,
        published_app_id=app.id,
        published_app_account_id=app_account.id,
        thread_id=child_thread.id,
        input_params={"input": "child thread"},
        parent_run_id=run.id,
        root_run_id=run.id,
        depth=1,
    )
    db_session.add(child_run)
    await db_session.flush()
    await thread_service.start_turn(
        thread_id=child_thread.id,
        run_id=child_run.id,
        user_input_text="child thread",
    )
    await thread_service.complete_turn(
        run_id=child_run.id,
        status=AgentThreadTurnStatus.completed,
        assistant_output_text="child response",
        metadata={"final_output": "child response"},
    )
    await db_session.commit()

    thread_resp = await client.get(
        f"/_talmudpedia/threads/{resolved.thread.id}?include_subthreads=true",
        headers=_host_headers(app.public_id),
    )
    assert thread_resp.status_code == 200
    payload = thread_resp.json()
    assert payload["lineage"]["root_thread_id"] == str(resolved.thread.id)
    assert payload["subthread_tree"]["children"][0]["thread"]["id"] == str(child_thread.id)


@pytest.mark.asyncio
async def test_legacy_public_published_path_endpoints_return_410(client, db_session):
    tenant, owner, _, agent = await seed_admin_tenant_and_agent(db_session)
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        owner.id,
        slug="legacy-path-cut-app",
        auth_enabled=True,
        auth_providers=["password"],
    )

    runtime_resp = await client.get(f"/public/apps/{app.public_id}/runtime")
    assert runtime_resp.status_code == 410

    signup_resp = await client.post(
        f"/public/apps/{app.public_id}/auth/signup",
        json={"email": "legacy@example.com", "password": "secret123"},
    )
    assert signup_resp.status_code == 410

    chat_resp = await client.post(
        f"/public/apps/{app.public_id}/chat/stream",
        json={"input": "hello"},
    )
    assert chat_resp.status_code == 410


@pytest.mark.asyncio
async def test_host_assets_serve_dist_asset_with_assets_prefix(client, db_session, monkeypatch):
    tenant, owner, _, agent = await seed_admin_tenant_and_agent(db_session)
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        owner.id,
        slug="host-assets-app",
        auth_enabled=False,
        auth_providers=["password"],
    )

    revision = PublishedAppRevision(
        published_app_id=app.id,
        kind=PublishedAppRevisionKind.published,
        template_key="classic-chat",
        template_runtime="vite_static",
        files={"src/main.tsx": "export default {};"},
        dist_storage_prefix="apps/t/a/revisions/host-assets/dist",
        dist_manifest={"entry_html": "index.html"},
        created_by=owner.id,
    )
    db_session.add(revision)
    await db_session.flush()
    app.current_published_revision_id = revision.id
    await db_session.commit()

    class _Storage:
        def read_asset_bytes(self, *, dist_storage_prefix: str, asset_path: str):
            assert dist_storage_prefix == "apps/t/a/revisions/host-assets/dist"
            assert asset_path == "assets/index-abc123.js"
            return b"console.log('ok')", "application/javascript"

    monkeypatch.setattr(
        "app.api.routers.published_apps_host_runtime.PublishedAppBundleStorage.from_env",
        staticmethod(lambda: _Storage()),
    )

    resp = await client.get("/assets/index-abc123.js", headers=_host_headers(app.public_id))
    assert resp.status_code == 200
    assert "console.log('ok')" in resp.text


@pytest.mark.asyncio
async def test_host_assets_are_private_cache_when_auth_enabled(client, db_session, monkeypatch):
    tenant, owner, _, agent = await seed_admin_tenant_and_agent(db_session)
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        owner.id,
        slug="host-private-assets-app",
        auth_enabled=True,
        auth_providers=["password"],
    )

    revision = PublishedAppRevision(
        published_app_id=app.id,
        kind=PublishedAppRevisionKind.published,
        template_key="classic-chat",
        template_runtime="vite_static",
        files={"src/main.tsx": "export default {};"},
        dist_storage_prefix="apps/t/a/revisions/host-private-assets/dist",
        dist_manifest={"entry_html": "index.html"},
        created_by=owner.id,
    )
    db_session.add(revision)
    await db_session.flush()
    app.current_published_revision_id = revision.id
    await db_session.commit()

    class _Storage:
        def read_asset_bytes(self, *, dist_storage_prefix: str, asset_path: str):
            assert dist_storage_prefix == "apps/t/a/revisions/host-private-assets/dist"
            assert asset_path == "assets/index-auth.js"
            return b"console.log('private')", "application/javascript"

    monkeypatch.setattr(
        "app.api.routers.published_apps_host_runtime.PublishedAppBundleStorage.from_env",
        staticmethod(lambda: _Storage()),
    )

    signup_resp = await client.post(
        "/_talmudpedia/auth/signup",
        headers=_host_headers(app.public_id),
        json={"email": "asset-user@example.com", "password": "secret123"},
    )
    assert signup_resp.status_code == 200

    resp = await client.get("/assets/index-auth.js", headers=_host_headers(app.public_id))
    assert resp.status_code == 200
    assert resp.headers["Cache-Control"] == "private, max-age=60"


@pytest.mark.asyncio
async def test_host_login_rate_limits_repeated_failed_password_attempts(client, db_session):
    tenant, owner, _, agent = await seed_admin_tenant_and_agent(db_session)
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        owner.id,
        slug="host-login-throttle-app",
        auth_enabled=True,
        auth_providers=["password"],
    )

    signup_resp = await client.post(
        "/_talmudpedia/auth/signup",
        headers=_host_headers(app.public_id),
        json={"email": "throttle-user@example.com", "password": "secret123"},
    )
    assert signup_resp.status_code == 200

    for _ in range(4):
        resp = await client.post(
            "/_talmudpedia/auth/login",
            headers=_host_headers(app.public_id),
            json={"email": "throttle-user@example.com", "password": "wrong-password"},
        )
        assert resp.status_code == 400

    locked_resp = await client.post(
        "/_talmudpedia/auth/login",
        headers=_host_headers(app.public_id),
        json={"email": "throttle-user@example.com", "password": "wrong-password"},
    )
    assert locked_resp.status_code == 429
    assert locked_resp.json()["detail"] == "Too many failed login attempts. Try again later."


@pytest.mark.asyncio
async def test_host_google_start_sets_csrf_state_cookie(client, db_session, monkeypatch):
    tenant, owner, _, agent = await seed_admin_tenant_and_agent(db_session)
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        owner.id,
        slug="host-google-start-app",
        auth_enabled=True,
        auth_providers=["google"],
    )

    async def _fake_get_google_credential(self, organization_id):
        assert str(organization_id) == str(app.organization_id)
        return SimpleNamespace(credentials={"client_id": "google-client", "redirect_uri": "https://accounts.example/callback"})

    monkeypatch.setattr("app.services.published_app_auth_service.PublishedAppAuthService.get_google_credential", _fake_get_google_credential)

    response = await client.get(
        "/_talmudpedia/auth/google/start?return_to=/dashboard",
        headers=_host_headers(app.public_id),
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "published_app_google_oauth_state=" in response.headers.get("set-cookie", "")
    state = parse_qs(urlparse(response.headers["location"]).query)["state"][0]
    assert state


@pytest.mark.asyncio
async def test_host_google_callback_rejects_missing_csrf_state_cookie(client, db_session, monkeypatch):
    tenant, owner, _, agent = await seed_admin_tenant_and_agent(db_session)
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        owner.id,
        slug="host-google-callback-app",
        auth_enabled=True,
        auth_providers=["google"],
    )

    async def _fake_get_google_credential(self, organization_id):
        assert str(organization_id) == str(app.organization_id)
        return SimpleNamespace(
            credentials={
                "client_id": "google-client",
                "client_secret": "google-secret",
                "redirect_uri": "https://accounts.example/callback",
            }
        )

    monkeypatch.setattr("app.services.published_app_auth_service.PublishedAppAuthService.get_google_credential", _fake_get_google_credential)

    start_response = await client.get(
        "/_talmudpedia/auth/google/start?return_to=/dashboard",
        headers=_host_headers(app.public_id),
        follow_redirects=False,
    )
    state = parse_qs(urlparse(start_response.headers["location"]).query)["state"][0]
    client.cookies.clear()

    callback_resp = await client.get(
        f"/_talmudpedia/auth/google/callback?code=fake-code&state={state}",
        headers=_host_headers(app.public_id),
        follow_redirects=False,
    )

    assert callback_resp.status_code == 400
    assert "Invalid OAuth state" in callback_resp.json()["detail"]
