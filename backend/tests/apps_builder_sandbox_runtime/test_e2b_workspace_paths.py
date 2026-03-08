from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.published_app_sandbox_backend_e2b_workspace import E2BSandboxWorkspaceMixin


class _WorkspaceHarness(E2BSandboxWorkspaceMixin):
    config = SimpleNamespace(e2b_workspace_path="/workspace")

    async def _run_shell(self, sandbox, command: str, **kwargs):
        _ = sandbox, command, kwargs
        return SimpleNamespace(
            stdout="./src/main.tsx\n./.draft-dev-dependency-hash\n./.env.example\n./nested/.env.example\n",
            stderr="",
            exit_code=0,
        )


@pytest.mark.asyncio
async def test_list_workspace_paths_preserves_hidden_marker_filenames():
    harness = _WorkspaceHarness()
    rows = await harness._list_workspace_paths(object(), "/workspace")
    assert ".draft-dev-dependency-hash" not in rows
    assert "draft-dev-dependency-hash" not in rows
    assert ".env.example" in rows
    assert "src/main.tsx" in rows
    assert "nested/.env.example" in rows
