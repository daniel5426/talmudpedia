from uuid import uuid4

import pytest

from app.db.postgres.models.identity import User
from tests.published_apps._helpers import admin_headers


@pytest.mark.asyncio
async def test_settings_profile_get_and_patch(client, db_session):
    user = User(
        email=f"profile-{uuid4().hex[:8]}@example.com",
        hashed_password="x",
        role="admin",
        full_name="Before Name",
        avatar="https://example.com/old.png",
    )
    db_session.add(user)
    await db_session.commit()

    headers = admin_headers(str(user.id), str(uuid4()), str(uuid4()))

    get_resp = await client.get("/api/settings/profile", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["full_name"] == "Before Name"

    patch_resp = await client.patch(
        "/api/settings/profile",
        headers=headers,
        json={"full_name": "After Name", "avatar": "https://example.com/new.png"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["full_name"] == "After Name"
    assert patch_resp.json()["avatar"] == "https://example.com/new.png"
