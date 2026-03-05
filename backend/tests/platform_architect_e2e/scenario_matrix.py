from __future__ import annotations

from dataclasses import dataclass
from typing import List

from app.services.platform_architect_contracts import PLATFORM_ARCHITECT_DOMAIN_TOOLS


@dataclass(frozen=True)
class ScenarioDefinition:
    id: str
    tool_slug: str
    target_action: str
    expected_outcome: str  # success | expected_block
    expected_error_code: str | None
    requires_model: bool


EXPECTED_BLOCK_BY_ACTION = {
    "agents.publish": "DRAFT_FIRST_POLICY_DENIED",
    "tools.publish": "DRAFT_FIRST_POLICY_DENIED",
    "artifacts.promote": "DRAFT_FIRST_POLICY_DENIED",
    "orchestration.spawn_run": "feature_disabled",
    "orchestration.spawn_group": "feature_disabled",
    "orchestration.join": "feature_disabled",
    "orchestration.cancel_subtree": "feature_disabled",
    "orchestration.evaluate_and_replan": "feature_disabled",
    "orchestration.query_tree": "feature_disabled",
}

MODEL_REQUIRED_ACTIONS = {
    "agents.create",
    "agents.execute",
    "agents.start_run",
}


def _stable_id(action: str) -> str:
    return action.replace(".", "_")


def build_scenarios() -> List[ScenarioDefinition]:
    scenarios: list[ScenarioDefinition] = []

    for tool_slug, spec in PLATFORM_ARCHITECT_DOMAIN_TOOLS.items():
        for action in sorted(spec.get("actions", {}).keys()):
            expected_code = EXPECTED_BLOCK_BY_ACTION.get(action)
            expected_outcome = "expected_block" if expected_code else "success"
            scenarios.append(
                ScenarioDefinition(
                    id=_stable_id(action),
                    tool_slug=tool_slug,
                    target_action=action,
                    expected_outcome=expected_outcome,
                    expected_error_code=expected_code,
                    requires_model=action in MODEL_REQUIRED_ACTIONS,
                )
            )

    return scenarios


SCENARIOS: List[ScenarioDefinition] = build_scenarios()
