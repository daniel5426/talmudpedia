from pathlib import Path


def test_no_legacy_api_agents_refs_in_control_plane_sdk_and_tool_paths() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    scan_roots = [
        repo_root / "backend" / "talmudpedia_control_sdk",
        repo_root / "backend" / "artifacts" / "builtin" / "platform_sdk",
    ]

    offenders: list[str] = []
    for root in scan_roots:
        for file_path in root.rglob("*.py"):
            text = file_path.read_text(encoding="utf-8")
            for line_no, line in enumerate(text.splitlines(), start=1):
                if "/api/agents" in line:
                    rel = file_path.relative_to(repo_root)
                    offenders.append(f"{rel}:{line_no}")

    assert not offenders, "Legacy /api/agents references found in control-plane SDK/tool code: " + ", ".join(offenders)
