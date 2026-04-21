from __future__ import annotations

from uuid import uuid4

import pytest

from app.api.routers.models import list_models
from app.db.postgres.models.identity import Organization, User
from app.db.postgres.models.registry import ModelCapabilityType, ModelRegistry, ModelStatus
from app.services import platform_native_tools
from app.services.control_plane.context import ControlPlaneContext
from app.services.control_plane.models_service import ListModelsInput, ModelRegistryService


@pytest.mark.asyncio
async def test_models_list_matches_service_router_and_native_tool(db_session, monkeypatch):
    tenant = Organization(name="Parity Organization", slug=f"parity-{uuid4().hex[:8]}")
    user = User(email=f"parity-{uuid4().hex[:8]}@example.com", hashed_password="x", role="admin")
    db_session.add_all([tenant, user])
    await db_session.flush()
    db_session.add_all(
        [
            ModelRegistry(
                organization_id=tenant.id,
                name="Chat Active",
                capability_type=ModelCapabilityType.CHAT,
                status=ModelStatus.ACTIVE,
                is_active=True,
                metadata_={},
            ),
            ModelRegistry(
                organization_id=tenant.id,
                name="Chat Disabled",
                capability_type=ModelCapabilityType.CHAT,
                status=ModelStatus.DISABLED,
                is_active=False,
                metadata_={},
            ),
        ]
    )
    await db_session.commit()

    ctx = ControlPlaneContext(
        organization_id=tenant.id,
        user=user,
        user_id=user.id,
        scopes=("*",),
    )
    service_models, service_total = await ModelRegistryService(db_session).list_models(
        ctx=ctx,
        params=ListModelsInput(capability_type=ModelCapabilityType.CHAT, status=ModelStatus.ACTIVE, is_active=True),
    )

    route_result = await list_models(
        capability_type=ModelCapabilityType.CHAT,
        status=ModelStatus.ACTIVE,
        is_active=True,
        skip=0,
        limit=20,
        view="summary",
        db=db_session,
        organization_ctx={"organization_id": str(tenant.id), "tenant": tenant},
        _={},
        principal={
            "type": "user",
            "user": user,
            "user_id": str(user.id),
            "organization_id": str(tenant.id),
            "scopes": ["*"],
        },
    )

    class _FakeSession:
        async def __aenter__(self):
            return db_session
        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(platform_native_tools, "get_session", lambda: _FakeSession())
    native_result = await platform_native_tools.platform_native_platform_assets(
        {
            "action": "models.list",
            "payload": {
                "capability_type": "chat",
                "status": "active",
                "is_active": True,
                "view": "summary",
            },
            "__tool_runtime_context__": {
                "organization_id": str(tenant.id),
                "user_id": str(user.id),
                "scopes": ["*"],
            },
        }
    )

    service_names = [model.name for model in service_models]
    route_names = [model["name"] for model in route_result["items"]]
    native_payload = native_result["result"]
    native_items = native_payload.get("items") or native_payload.get("models") or native_payload.get("data", {}).get("items") or []
    native_names = [model["name"] for model in native_items]

    assert "Chat Active" in service_names
    assert "Chat Disabled" not in service_names
    assert route_result["total"] == service_total
    assert route_names == service_names[: len(route_names)]
    assert native_result["errors"] == []
    native_total = native_payload.get("total")
    if native_total is None and isinstance(native_payload.get("data"), dict):
        native_total = native_payload["data"].get("total")
    assert native_total == service_total
    assert native_names == service_names[: len(native_names)]
