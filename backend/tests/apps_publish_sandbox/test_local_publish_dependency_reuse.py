from pathlib import Path

import pytest

from app.services.published_app_draft_dev_local_runtime import (
    LocalDraftDevRuntimeManager,
    _SessionProcess,
)


class _DummyProcess:
    def poll(self):
        return None


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _session_state(project_dir: Path) -> _SessionProcess:
    return _SessionProcess(
        sandbox_id="sandbox-1",
        project_dir=project_dir,
        port=5173,
        process=_DummyProcess(),  # type: ignore[arg-type]
        dependency_hash="dep-hash",
        revision_seq=1,
    )


@pytest.mark.asyncio
async def test_prepare_publish_dependencies_reuses_live_workspace_node_modules(tmp_path: Path) -> None:
    manager = LocalDraftDevRuntimeManager()
    project_dir = tmp_path / "sandbox"

    _write_text(project_dir / "package.json", '{"name":"demo"}')
    _write_text(project_dir / "package-lock.json", '{"lockfileVersion":3}')
    _write_text(project_dir / "node_modules" / "dep" / "index.js", "module.exports = 1;")

    manager._state["sandbox-1"] = _session_state(project_dir)  # noqa: SLF001

    result = await manager.prepare_publish_dependencies(
        sandbox_id="sandbox-1",
        workspace_path=str(project_dir),
    )

    assert result["status"] == "reused"
    assert result["strategy"] == "live"
    assert (project_dir / "node_modules" / "dep" / "index.js").exists()


@pytest.mark.asyncio
async def test_prepare_publish_dependencies_falls_back_when_live_modules_missing(tmp_path: Path) -> None:
    manager = LocalDraftDevRuntimeManager()
    project_dir = tmp_path / "sandbox"

    _write_text(project_dir / "package.json", '{"name":"demo"}')

    manager._state["sandbox-1"] = _session_state(project_dir)  # noqa: SLF001

    result = await manager.prepare_publish_dependencies(
        sandbox_id="sandbox-1",
        workspace_path=str(project_dir),
    )

    assert result["status"] == "missing_live_node_modules"
    assert result["strategy"] == "none"
