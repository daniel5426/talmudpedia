from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class E2EReport:
    def __init__(self, tenant_id: str, path: str):
        self.tenant_id = tenant_id
        self.path = Path(path)
        self.started_at = datetime.now(timezone.utc)
        self.results: list[dict[str, Any]] = []

    def add_result(self, entry: dict[str, Any]) -> None:
        self.results.append(entry)

    def flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        ended = datetime.now(timezone.utc)
        passed = sum(1 for r in self.results if r.get("status") == "passed")
        failed = sum(1 for r in self.results if r.get("status") == "failed")
        payload = {
            "run_id": f"arch-e2e-{int(self.started_at.timestamp())}",
            "tenant_id": self.tenant_id,
            "started_at": self.started_at.isoformat(),
            "ended_at": ended.isoformat(),
            "scenarios_total": len(self.results),
            "scenarios_passed": passed,
            "scenarios_failed": failed,
            "results": self.results,
        }
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
