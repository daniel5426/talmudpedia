from __future__ import annotations

from typing import Any


def build_authoring_issue(
    *,
    code: str,
    message: str,
    severity: str = "error",
    node_id: str | None = None,
    edge_id: str | None = None,
    path: str | None = None,
    expected: Any = None,
    actual: Any = None,
    suggestions: list[str] | None = None,
    suggested_value: Any = None,
    repair_hint: str | None = None,
) -> dict[str, Any]:
    return {
        "code": str(code),
        "message": str(message),
        "severity": str(severity),
        "node_id": node_id,
        "edge_id": edge_id,
        "path": path,
        "expected": expected,
        "actual": actual,
        "suggestions": list(suggestions or []) or None,
        "suggested_value": suggested_value,
        "repair_hint": repair_hint,
    }


def dedupe_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for issue in issues:
        signature = (
            issue.get("code"),
            issue.get("node_id"),
            issue.get("edge_id"),
            issue.get("path"),
            issue.get("message"),
            issue.get("severity"),
        )
        if signature in seen:
            continue
        seen.add(signature)
        deduped.append(issue)
    return deduped
