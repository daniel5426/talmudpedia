import jwt
import pytest
from uuid import UUID
from sqlalchemy import func, select

from app.core.security import ALGORITHM, SECRET_KEY
from app.db.postgres.models.agent_threads import AgentThread, AgentThreadTurn
from app.db.postgres.models.agents import AgentRun
from app.db.postgres.models.identity import User
from app.db.postgres.models.published_apps import PublishedAppAccount, PublishedAppRevision, PublishedAppRevisionBuildStatus, PublishedAppRevisionKind
from app.services.published_app_auth_service import AuthResult
from app.services.security_bootstrap_service import SecurityBootstrapService
from tests.published_apps._helpers import install_stub_agent_worker, seed_admin_tenant_and_agent, seed_published_app


ALLOWED_ORIGIN = "https://client.example.com"


async def _attach_published_revision(db_session, app, *, created_by):
    revision = PublishedAppRevision(
        published_app_id=app.id,
        kind=PublishedAppRevisionKind.published,
        template_key=app.template_key,
        entry_file="src/main.tsx",
        files={},
        manifest_json={},
        build_status=PublishedAppRevisionBuildStatus.succeeded,
        version_seq=1,
        origin_kind="test",
        created_by=created_by,
    )
    db_session.add(revision)
    await db_session.flush()
    app.current_published_revision_id = revision.id
    await db_session.commit()
    await db_session.refresh(app)
    return revision


def _external_headers(token: str | None = None, *, origin: str = ALLOWED_ORIGIN) -> dict[str, str]:
    headers = {"Origin": origin}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _token_with_scopes(token: str, scopes: list[str]) -> str:
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    payload["scope"] = scopes
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


async def _grant_member_role(db_session, *, organization_id, owner_id, email: str):
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    bootstrap = SecurityBootstrapService(db_session)
    await bootstrap.ensure_default_roles(organization_id)
    await bootstrap.ensure_organization_reader_assignment(
        organization_id=organization_id,
        user_id=user.id,
        assigned_by=owner_id,
    )
    await db_session.commit()


@pytest.mark.asyncio
async def test_external_runtime_bootstrap_returns_external_stream_contract(client, db_session):
    tenant, owner, _, agent = await seed_admin_tenant_and_agent(db_session)
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        owner.id,
        slug="external-bootstrap-app",
        allowed_origins=[ALLOWED_ORIGIN],
    )
    revision = await _attach_published_revision(db_session, app, created_by=owner.id)

    resp = await client.get(
        f"/public/external/apps/{app.public_id}/runtime/bootstrap",
        headers=_external_headers(),
    )
    assert resp.status_code == 200
    assert resp.headers["Access-Control-Allow-Origin"] == ALLOWED_ORIGIN
    payload = resp.json()
    assert payload["revision_id"] == str(revision.id)
    assert payload["chat_stream_url"].endswith(f"/public/external/apps/{app.public_id}/chat/stream")
    assert payload["auth"]["enabled"] is True


@pytest.mark.asyncio
async def test_external_password_auth_flow_uses_bearer_tokens(client, db_session):
    tenant, owner, _, agent = await seed_admin_tenant_and_agent(db_session)
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        owner.id,
        slug="external-auth-app",
        allowed_origins=[ALLOWED_ORIGIN],
    )

    signup_resp = await client.post(
        f"/public/external/apps/{app.public_id}/auth/signup",
        headers=_external_headers(),
        json={"email": "external-user@example.com", "password": "secret123"},
    )
    assert signup_resp.status_code == 200
    token = signup_resp.json()["token"]
    assert signup_resp.json()["token_type"] == "bearer"

    await _grant_member_role(
        db_session,
        organization_id=tenant.id,
        owner_id=owner.id,
        email="external-user@example.com",
    )

    me_resp = await client.get(
        f"/public/external/apps/{app.public_id}/auth/me",
        headers=_external_headers(token),
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "external-user@example.com"

    logout_resp = await client.post(
        f"/public/external/apps/{app.public_id}/auth/logout",
        headers=_external_headers(token),
    )
    assert logout_resp.status_code == 200
    assert logout_resp.json()["status"] == "logged_out"

    me_after_logout = await client.get(
        f"/public/external/apps/{app.public_id}/auth/me",
        headers=_external_headers(token),
    )
    assert me_after_logout.status_code == 401


@pytest.mark.asyncio
async def test_external_runtime_rejects_cross_app_bearer_replay(client, db_session):
    tenant, owner, _, agent = await seed_admin_tenant_and_agent(db_session)
    app_a = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        owner.id,
        slug="external-replay-app-a",
        allowed_origins=[ALLOWED_ORIGIN],
    )
    app_b = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        owner.id,
        slug="external-replay-app-b",
        allowed_origins=[ALLOWED_ORIGIN],
    )

    signup_resp = await client.post(
        f"/public/external/apps/{app_a.public_id}/auth/signup",
        headers=_external_headers(),
        json={"email": "replay-user@example.com", "password": "secret123"},
    )
    token = signup_resp.json()["token"]

    replay_resp = await client.get(
        f"/public/external/apps/{app_b.public_id}/auth/me",
        headers=_external_headers(token),
    )
    assert replay_resp.status_code == 403
    assert replay_resp.json()["detail"] == "Token does not belong to this app"


@pytest.mark.asyncio
async def test_external_runtime_enforces_published_app_scopes(client, db_session):
    tenant, owner, _, agent = await seed_admin_tenant_and_agent(db_session)
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        owner.id,
        slug="external-scope-app",
        allowed_origins=[ALLOWED_ORIGIN],
    )

    signup_resp = await client.post(
        f"/public/external/apps/{app.public_id}/auth/signup",
        headers=_external_headers(),
        json={"email": "scoped-user@example.com", "password": "secret123"},
    )
    token = signup_resp.json()["token"]

    me_resp = await client.get(
        f"/public/external/apps/{app.public_id}/auth/me",
        headers=_external_headers(_token_with_scopes(token, ["public.chat", "public.chats.read"])),
    )
    assert me_resp.status_code == 403
    assert me_resp.json()["detail"] == "Missing required scopes: public.auth"

    chat_resp = await client.post(
        f"/public/external/apps/{app.public_id}/chat/stream",
        headers=_external_headers(_token_with_scopes(token, ["public.auth", "public.chats.read"])),
        json={"input": "hello"},
    )
    assert chat_resp.status_code == 403
    assert chat_resp.json()["detail"] == "Missing required scopes: public.chat"

    threads_resp = await client.get(
        f"/public/external/apps/{app.public_id}/threads",
        headers=_external_headers(_token_with_scopes(token, ["public.auth", "public.chat"])),
    )
    assert threads_resp.status_code == 403
    assert threads_resp.json()["detail"] == "Missing required scopes: public.chats.read"


@pytest.mark.asyncio
async def test_external_auth_exchange_returns_bearer_session(client, db_session, monkeypatch):
    tenant, owner, _, agent = await seed_admin_tenant_and_agent(db_session)
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        owner.id,
        slug="external-exchange-app",
        allowed_origins=[ALLOWED_ORIGIN],
        external_auth_oidc={
            "issuer": "https://issuer.example.com",
            "audience": "aud-1",
            "jwks_uri": "https://issuer.example.com/.well-known/jwks.json",
        },
    )

    async def fake_exchange(self, *, app, token):
        account = await self._get_account_by_email(app_id=app.id, email="oidc-user@example.com")
        if account is None:
            account = await self._create_account(
                app=app,
                email="oidc-user@example.com",
                full_name="OIDC User",
            )
        return await self.issue_auth_result(app=app, account=account, provider="oidc", metadata={"token": token})

    monkeypatch.setattr(
        "app.api.routers.published_apps_external_runtime.PublishedAppAuthService.exchange_external_oidc",
        fake_exchange,
    )

    resp = await client.post(
        f"/public/external/apps/{app.public_id}/auth/exchange",
        headers=_external_headers(),
        json={"token": "oidc-token"},
    )
    assert resp.status_code == 200
    assert resp.json()["token_type"] == "bearer"
    assert resp.json()["user"]["email"] == "oidc-user@example.com"


@pytest.mark.asyncio
async def test_external_stream_persists_thread_and_history_is_scoped(client, db_session, monkeypatch):
    tenant, owner, _, agent = await seed_admin_tenant_and_agent(db_session)
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        owner.id,
        slug="external-threads-app",
        allowed_origins=[ALLOWED_ORIGIN],
    )

    signup_resp = await client.post(
        f"/public/external/apps/{app.public_id}/auth/signup",
        headers=_external_headers(),
        json={"email": "thread-user-one@example.com", "password": "secret123"},
    )
    token_one = signup_resp.json()["token"]
    await _grant_member_role(
        db_session,
        organization_id=tenant.id,
        owner_id=owner.id,
        email="thread-user-one@example.com",
    )

    install_stub_agent_worker(monkeypatch, content="Hello from external runtime")

    stream_resp = await client.post(
        f"/public/external/apps/{app.public_id}/chat/stream",
        headers=_external_headers(token_one),
        json={"input": "hello"},
    )
    assert stream_resp.status_code == 200
    assert stream_resp.headers["Access-Control-Allow-Origin"] == ALLOWED_ORIGIN
    assert "Hello from external runtime" in stream_resp.text
    thread_id = stream_resp.headers.get("X-Thread-ID")
    assert thread_id

    thread_count = await db_session.scalar(
        select(func.count(AgentThread.id)).where(AgentThread.published_app_id == app.id)
    )
    assert thread_count == 1

    list_resp = await client.get(
        f"/public/external/apps/{app.public_id}/threads",
        headers=_external_headers(token_one),
    )
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] == 1
    assert list_resp.json()["items"][0]["id"] == thread_id

    detail_resp = await client.get(
        f"/public/external/apps/{app.public_id}/threads/{thread_id}",
        headers=_external_headers(token_one),
    )
    assert detail_resp.status_code == 200
    assert detail_resp.json()["id"] == thread_id

    logout_one = await client.post(
        f"/public/external/apps/{app.public_id}/auth/logout",
        headers=_external_headers(token_one),
    )
    assert logout_one.status_code == 200

    signup_two = await client.post(
        f"/public/external/apps/{app.public_id}/auth/signup",
        headers=_external_headers(),
        json={"email": "thread-user-two@example.com", "password": "secret123"},
    )
    token_two = signup_two.json()["token"]
    await _grant_member_role(
        db_session,
        organization_id=tenant.id,
        owner_id=owner.id,
        email="thread-user-two@example.com",
    )

    other_detail = await client.get(
        f"/public/external/apps/{app.public_id}/threads/{thread_id}",
        headers=_external_headers(token_two),
    )
    assert other_detail.status_code == 404


@pytest.mark.asyncio
async def test_external_thread_detail_returns_subthread_tree_when_requested(client, db_session, monkeypatch):
    tenant, owner, _, agent = await seed_admin_tenant_and_agent(db_session)
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        owner.id,
        slug="external-subthreads-app",
        allowed_origins=[ALLOWED_ORIGIN],
    )

    signup_resp = await client.post(
        f"/public/external/apps/{app.public_id}/auth/signup",
        headers=_external_headers(),
        json={"email": "subthreads@example.com", "password": "secret123"},
    )
    token = signup_resp.json()["token"]
    await _grant_member_role(
        db_session,
        organization_id=tenant.id,
        owner_id=owner.id,
        email="subthreads@example.com",
    )

    install_stub_agent_worker(monkeypatch, content="Hello from external runtime")

    stream_resp = await client.post(
        f"/public/external/apps/{app.public_id}/chat/stream",
        headers=_external_headers(token),
        json={"input": "hello"},
    )
    thread_id = UUID(str(stream_resp.headers["X-Thread-ID"]))
    root_thread = await db_session.get(AgentThread, thread_id)
    assert root_thread is not None
    root_run = await db_session.scalar(select(AgentRun).where(AgentRun.thread_id == root_thread.id).limit(1))
    root_turn = await db_session.scalar(select(AgentThreadTurn).where(AgentThreadTurn.run_id == root_run.id).limit(1))
    assert root_run is not None
    if root_turn is None:
        root_turn = AgentThreadTurn(
            thread_id=root_thread.id,
            run_id=root_run.id,
            turn_index=0,
            user_input_text="hello",
            assistant_output_text="Hello from external runtime",
        )
        db_session.add(root_turn)
        await db_session.flush()

    child_thread = AgentThread(
        organization_id=tenant.id,
        project_id=app.project_id,
        app_account_id=root_thread.app_account_id,
        agent_id=agent.id,
        published_app_id=app.id,
        surface=root_thread.surface,
        title="External child thread",
        root_thread_id=root_thread.id,
        parent_thread_id=root_thread.id,
        parent_thread_turn_id=root_turn.id,
        spawned_by_run_id=root_run.id,
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
        published_app_account_id=root_thread.app_account_id,
        thread_id=child_thread.id,
        input_params={"input": "child hello"},
        parent_run_id=root_run.id,
        root_run_id=root_run.id,
        depth=1,
    )
    db_session.add(child_run)
    await db_session.flush()
    db_session.add(
        AgentThreadTurn(
            thread_id=child_thread.id,
            run_id=child_run.id,
            turn_index=0,
            user_input_text="child hello",
            assistant_output_text="child response",
        )
    )
    await db_session.commit()

    detail_resp = await client.get(
        f"/public/external/apps/{app.public_id}/threads/{thread_id}",
        headers=_external_headers(token),
        params={"include_subthreads": "true"},
    )
    assert detail_resp.status_code == 200
    payload = detail_resp.json()
    assert payload["lineage"]["root_thread_id"] == str(root_thread.id)
    assert payload["subthread_tree"]["children"][0]["thread"]["id"] == str(child_thread.id)


@pytest.mark.asyncio
async def test_external_stream_is_ephemeral_when_app_auth_disabled(client, db_session, monkeypatch):
    tenant, owner, _, agent = await seed_admin_tenant_and_agent(db_session)
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        owner.id,
        slug="external-public-app",
        auth_enabled=False,
        auth_providers=[],
        allowed_origins=[ALLOWED_ORIGIN],
    )

    install_stub_agent_worker(monkeypatch, content="Public response")

    resp = await client.post(
        f"/public/external/apps/{app.public_id}/chat/stream",
        headers=_external_headers(),
        json={"input": "public prompt"},
    )
    assert resp.status_code == 200
    assert "Public response" in resp.text
    assert resp.headers.get("X-Thread-ID") is None

    thread_count = await db_session.scalar(
        select(func.count(AgentThread.id)).where(AgentThread.published_app_id == app.id)
    )
    assert thread_count == 0


@pytest.mark.asyncio
async def test_external_runtime_rejects_blocked_origin(client, db_session):
    tenant, owner, _, agent = await seed_admin_tenant_and_agent(db_session)
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        owner.id,
        slug="external-cors-app",
        allowed_origins=[ALLOWED_ORIGIN],
    )

    blocked_resp = await client.get(
        f"/public/external/apps/{app.public_id}/runtime/bootstrap",
        headers=_external_headers(origin="https://blocked.example.com"),
    )
    assert blocked_resp.status_code == 403
    assert blocked_resp.json()["detail"] == "Origin is not allowed for this published app"
