from __future__ import annotations

from pathlib import Path

import pytest

from app.services.published_app_draft_dev_local_runtime import LocalDraftDevRuntimeManager, _SessionProcess


class _FakeProcess:
    def poll(self):
        return None


def _make_manager(tmp_path: Path) -> tuple[LocalDraftDevRuntimeManager, str]:
    manager = LocalDraftDevRuntimeManager()
    sandbox_id = "sandbox-test"
    project_dir = tmp_path / sandbox_id
    project_dir.mkdir(parents=True, exist_ok=True)
    manager._state[sandbox_id] = _SessionProcess(  # type: ignore[attr-defined]
        sandbox_id=sandbox_id,
        project_dir=project_dir,
        port=3000,
        process=_FakeProcess(),  # type: ignore[arg-type]
        dependency_hash="dep-hash",
        revision_seq=1,
    )
    return manager, sandbox_id


@pytest.mark.asyncio
async def test_apply_patch_success_is_atomic_and_updates_file(tmp_path: Path):
    manager, sandbox_id = _make_manager(tmp_path)
    target = tmp_path / sandbox_id / "src" / "App.tsx"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("export const App = () => <main>old</main>;", encoding="utf-8")

    patch = """diff --git a/src/App.tsx b/src/App.tsx
--- a/src/App.tsx
+++ b/src/App.tsx
@@ -1 +1 @@
-export const App = () => <main>old</main>;
+export const App = () => <main>new</main>;
"""

    result = await manager.apply_patch(
        sandbox_id=sandbox_id,
        patch=patch,
        options={"atomic": True, "strip": 1, "allow_create": True, "allow_delete": True},
        preconditions={},
    )

    assert result["ok"] is True
    assert result["code"] == "PATCH_APPLIED"
    assert "src/App.tsx" in result["applied_files"]
    assert target.read_text(encoding="utf-8") == "export const App = () => <main>new</main>;"

    read_range = await manager.read_file_range(
        sandbox_id=sandbox_id,
        path="src/App.tsx",
        start_line=1,
        end_line=1,
        with_line_numbers=True,
    )
    assert "1: export const App = () => <main>new</main>;" in str(read_range["content"])


@pytest.mark.asyncio
async def test_apply_patch_hunk_mismatch_returns_failures_without_mutation(tmp_path: Path):
    manager, sandbox_id = _make_manager(tmp_path)
    target = tmp_path / sandbox_id / "src" / "App.tsx"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("export const App = () => <main>stable</main>;", encoding="utf-8")

    bad_patch = """diff --git a/src/App.tsx b/src/App.tsx
--- a/src/App.tsx
+++ b/src/App.tsx
@@ -1 +1 @@
-export const App = () => <main>old</main>;
+export const App = () => <main>changed</main>;
"""

    result = await manager.apply_patch(
        sandbox_id=sandbox_id,
        patch=bad_patch,
        options={"atomic": True, "strip": 1},
        preconditions={},
    )

    assert result["ok"] is False
    assert result["code"] == "PATCH_HUNK_MISMATCH"
    assert result["applied_files"] == []
    failures = result.get("failures") or []
    assert failures
    assert failures[0]["reason"] in {"context_mismatch", "deletion_mismatch"}
    assert target.read_text(encoding="utf-8") == "export const App = () => <main>stable</main>;"


@pytest.mark.asyncio
async def test_apply_patch_precondition_hash_mismatch(tmp_path: Path):
    manager, sandbox_id = _make_manager(tmp_path)
    target = tmp_path / sandbox_id / "src" / "App.tsx"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("export const App = () => <main>x</main>;", encoding="utf-8")

    patch = """diff --git a/src/App.tsx b/src/App.tsx
--- a/src/App.tsx
+++ b/src/App.tsx
@@ -1 +1 @@
-export const App = () => <main>x</main>;
+export const App = () => <main>y</main>;
"""
    result = await manager.apply_patch(
        sandbox_id=sandbox_id,
        patch=patch,
        options={"atomic": True, "strip": 1},
        preconditions={"expected_hashes": {"src/App.tsx": "sha256:deadbeef"}},
    )

    assert result["ok"] is False
    assert result["code"] == "PATCH_PRECONDITION_FAILED"
    assert target.read_text(encoding="utf-8") == "export const App = () => <main>x</main>;"


@pytest.mark.asyncio
async def test_workspace_index_returns_metadata_and_symbols(tmp_path: Path):
    manager, sandbox_id = _make_manager(tmp_path)
    app_file = tmp_path / sandbox_id / "src" / "feature.py"
    app_file.parent.mkdir(parents=True, exist_ok=True)
    app_file.write_text(
        "class Greeter:\n    pass\n\ndef run():\n    return 'ok'\n",
        encoding="utf-8",
    )

    index = await manager.workspace_index(
        sandbox_id=sandbox_id,
        limit=50,
        query="greeter",
        max_symbols_per_file=8,
    )

    assert index["total_files"] >= 1
    rows = index["files"]
    assert rows
    row = rows[0]
    assert row["path"] == "src/feature.py"
    assert row["language"] == "python"
    assert row["size_bytes"] > 0
    assert row["sha256"]
    assert any(symbol["name"] == "Greeter" for symbol in row.get("symbol_outline", []))


@pytest.mark.asyncio
async def test_apply_patch_accepts_begin_patch_update_file_format(tmp_path: Path):
    manager, sandbox_id = _make_manager(tmp_path)
    target = tmp_path / sandbox_id / "src" / "App.tsx"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "const extractReasoningStep = (event: RuntimeEvent): ReasoningStep | null => {\n"
        "  const data = event.data ||;\n"
        "  const statusRaw = typeof data.status === \"string\" ? data.status.toLowerCase() : \"\";\n"
        "}\n",
        encoding="utf-8",
    )

    patch = """*** Begin Patch
*** Update File: src/App.tsx
@@
 const extractReasoningStep = (event: RuntimeEvent): ReasoningStep | null => {
-  const data = event.data ||;
+  const data: any = event.data || (event as any) ||;
   const statusRaw = typeof data.status === "string" ? data.status.toLowerCase() : "";
*** End Patch"""

    result = await manager.apply_patch(
        sandbox_id=sandbox_id,
        patch=patch,
        options={"atomic": True, "strip": 1},
        preconditions={},
    )

    assert result["ok"] is True
    assert result["code"] == "PATCH_APPLIED"
    content = target.read_text(encoding="utf-8")
    assert "const data: any = event.data || (event as any) ||;" in content
