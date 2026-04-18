from __future__ import annotations

from uuid import uuid4

import pytest

from app.api.dependencies import get_current_principal
from app.db.postgres.models.agents import Agent
from app.db.postgres.models.identity import Tenant, User
from app.db.postgres.models.workspace import Project, ProjectStatus


def _principal_override(*, tenant: Tenant, project: Project, user: User, scopes: list[str] | None = None):
    async def _override():
        return {
            "type": "user",
            "user": user,
            "user_id": str(user.id),
            "tenant_id": str(tenant.id),
            "project_id": str(project.id),
            "scopes": scopes or ["files.read", "files.write", "agents.read", "agents.write", "agents.execute"],
            "auth_token": "test-token",
        }

    return _override


async def _seed_workspace(db_session):
    tenant = Tenant(name="Files Tenant", slug=f"files-tenant-{uuid4().hex[:8]}")
    user = User(email=f"files-{uuid4().hex[:8]}@example.com", hashed_password="x", role="admin")
    db_session.add_all([tenant, user])
    await db_session.flush()
    project = Project(
        organization_id=tenant.id,
        name="Files Project",
        slug=f"files-project-{uuid4().hex[:8]}",
        status=ProjectStatus.active,
        is_default=True,
        created_by=None,
    )
    agent = Agent(
        tenant_id=tenant.id,
        name="Files Workflow",
        slug=f"files-workflow-{uuid4().hex[:8]}",
        graph_definition={"nodes": [], "edges": []},
        memory_config={},
        execution_constraints={},
        created_by=None,
    )
    db_session.add_all([project, agent])
    await db_session.commit()
    return tenant, project, user, agent


@pytest.mark.asyncio
async def test_file_space_create_list_get_and_archive(client, db_session):
    tenant, project, user, _agent = await _seed_workspace(db_session)

    from main import app

    app.dependency_overrides[get_current_principal] = _principal_override(tenant=tenant, project=project, user=user)
    try:
        create_response = await client.post("/admin/files", json={"name": "Research", "description": "Workspace"})
        assert create_response.status_code == 201
        created = create_response.json()

        list_response = await client.get("/admin/files")
        assert list_response.status_code == 200
        items = list_response.json()["items"]
        assert [item["name"] for item in items] == ["Research"]

        get_response = await client.get(f"/admin/files/{created['id']}")
        assert get_response.status_code == 200
        assert get_response.json()["description"] == "Workspace"

        archive_response = await client.delete(f"/admin/files/{created['id']}")
        assert archive_response.status_code == 204

        after_archive = await client.get("/admin/files")
        assert after_archive.status_code == 200
        assert after_archive.json()["items"] == []
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_file_space_entry_crud_and_revisions(client, db_session):
    tenant, project, user, _agent = await _seed_workspace(db_session)

    from main import app

    app.dependency_overrides[get_current_principal] = _principal_override(tenant=tenant, project=project, user=user)
    try:
        create_response = await client.post("/admin/files", json={"name": "Research"})
        space_id = create_response.json()["id"]

        mkdir_response = await client.post(f"/admin/files/{space_id}/mkdir", json={"path": "raw/listings"})
        assert mkdir_response.status_code == 200
        assert mkdir_response.json()["path"] == "raw/listings"

        write_response = await client.put(
            f"/admin/files/{space_id}/entries/content",
            json={"path": "raw/listings/notes.md", "content": "hello city"},
        )
        assert write_response.status_code == 200
        first_revision_id = write_response.json()["revision"]["id"]

        read_response = await client.get(
            f"/admin/files/{space_id}/entries/content",
            params={"path": "raw/listings/notes.md"},
        )
        assert read_response.status_code == 200
        assert read_response.json()["content"] == "hello city"

        patch_response = await client.post(
            f"/admin/files/{space_id}/entries/patch",
            json={"path": "raw/listings/notes.md", "old_text": "city", "new_text": "market"},
        )
        assert patch_response.status_code == 200
        second_revision_id = patch_response.json()["revision"]["id"]
        assert second_revision_id != first_revision_id

        upload_response = await client.post(
            f"/admin/files/{space_id}/entries/upload",
            data={"path": "raw/listings/photo.bin"},
            files={"file": ("photo.bin", b"\x01\x02\x03", "application/octet-stream")},
        )
        assert upload_response.status_code == 200
        assert upload_response.json()["entry"]["is_text"] is False

        revisions_response = await client.get(
            f"/admin/files/{space_id}/entries/revisions",
            params={"path": "raw/listings/notes.md"},
        )
        assert revisions_response.status_code == 200
        assert len(revisions_response.json()["items"]) == 2

        move_response = await client.post(
            f"/admin/files/{space_id}/entries/move",
            json={"from_path": "raw/listings/notes.md", "to_path": "normalized/report.md"},
        )
        assert move_response.status_code == 200
        assert any(item["path"] == "normalized/report.md" for item in move_response.json()["items"])

        move_directory_response = await client.post(
            f"/admin/files/{space_id}/entries/move",
            json={"from_path": "raw/listings", "to_path": "normalized/listings"},
        )
        assert move_directory_response.status_code == 200
        moved_paths = {item["path"] for item in move_directory_response.json()["items"]}
        assert "normalized/listings" in moved_paths
        assert "normalized/listings/photo.bin" in moved_paths

        tree_response = await client.get(f"/admin/files/{space_id}/tree")
        assert tree_response.status_code == 200
        paths = {item["path"] for item in tree_response.json()["items"]}
        assert "normalized/report.md" in paths
        assert "normalized/listings/photo.bin" in paths

        delete_response = await client.post(
            f"/admin/files/{space_id}/entries/delete",
            json={"path": "raw"},
        )
        assert delete_response.status_code == 200

        final_tree = await client.get(f"/admin/files/{space_id}/tree")
        final_paths = {item["path"] for item in final_tree.json()["items"]}
        assert "raw/listings/photo.bin" not in final_paths
        assert "normalized/report.md" in final_paths
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_file_space_workflow_links_api(client, db_session):
    tenant, project, user, agent = await _seed_workspace(db_session)

    from main import app

    app.dependency_overrides[get_current_principal] = _principal_override(tenant=tenant, project=project, user=user)
    try:
        create_response = await client.post("/admin/files", json={"name": "Research"})
        space_id = create_response.json()["id"]

        link_response = await client.post(
            f"/admin/files/{space_id}/links",
            json={"agent_id": str(agent.id), "access_mode": "read_write"},
        )
        assert link_response.status_code == 200
        assert link_response.json()["access_mode"] == "read_write"

        list_response = await client.get(f"/admin/files/{space_id}/links")
        assert list_response.status_code == 200
        assert list_response.json()["items"][0]["agent_id"] == str(agent.id)

        delete_response = await client.delete(f"/admin/files/{space_id}/links/{agent.id}")
        assert delete_response.status_code == 204

        after_delete = await client.get(f"/admin/files/{space_id}/links")
        assert after_delete.json()["items"] == []
    finally:
        app.dependency_overrides.clear()
