import pytest

from app.services.artifact_runtime.dependency_registry import (
    analyze_artifact_dependencies,
    dependency_diagnostics_for_editor,
    normalize_dependency_name,
    verify_python_package_exists,
)


def test_analyze_artifact_dependencies_classifies_python_rows():
    rows = analyze_artifact_dependencies(
        language="python",
        source_files=[
            {
                "path": "main.py",
                "content": "import json\nimport httpx\nimport affine\nimport openai\nimport helpers\n",
            },
            {"path": "helpers.py", "content": "VALUE = 1\n"},
        ],
        dependencies=["openai"],
    )

    rows_by_name = {row["normalized_name"]: row for row in rows}
    assert rows_by_name["json"]["classification"] == "builtin"
    assert rows_by_name["httpx"]["classification"] == "runtime_provided"
    assert rows_by_name["httpx"]["source"] == "runtime_registry"
    assert rows_by_name["affine"]["classification"] == "runtime_provided"
    assert rows_by_name["affine"]["source"] == "runtime_catalog"
    assert rows_by_name["openai"]["classification"] == "declared"
    assert "helpers" not in rows_by_name


def test_analyze_artifact_dependencies_marks_missing_python_declaration():
    rows = analyze_artifact_dependencies(
        language="python",
        source_files=[{"path": "main.py", "content": "import openai\n"}],
        dependencies=[],
    )

    assert rows == [
        {
            "name": "openai",
            "normalized_name": "openai",
            "declared_spec": None,
            "classification": "runtime_provided",
            "source": "runtime_catalog",
            "status": "Runtime catalog",
            "note": "Listed in the official Pyodide package catalog, but not yet in the platform-verified runtime set.",
            "imported": True,
            "declared": False,
            "can_remove": False,
            "can_add": True,
            "needs_declaration": True,
        }
    ]


def test_dependency_diagnostics_for_editor_uses_runtime_registry():
    diagnostics = dependency_diagnostics_for_editor(
        language="python",
        source_files=[{"path": "main.py", "content": "import httpx\nimport affine\nimport openai\n"}],
        dependencies=[],
    )

    assert len(diagnostics) == 2
    assert all(item["code"] == "PYTHON_MISSING_DEPENDENCY" for item in diagnostics)
    assert {item["message"] for item in diagnostics} == {
        "Cannot resolve module 'affine'. Add it to artifact dependencies.",
        "Cannot resolve module 'openai'. Add it to artifact dependencies.",
    }


def test_normalize_dependency_name_handles_python_and_javascript_specs():
    assert normalize_dependency_name("python", "OpenAI>=1.0") == "openai"
    assert normalize_dependency_name("javascript", "@scope/pkg@1.2.3") == "@scope/pkg"
    assert normalize_dependency_name("javascript", "openai@4") == "openai"


@pytest.mark.asyncio
async def test_verify_python_package_exists_invalid_name_short_circuits():
    result = await verify_python_package_exists("bad package name")

    assert result["status"] == "invalid"
    assert result["exists"] is False
