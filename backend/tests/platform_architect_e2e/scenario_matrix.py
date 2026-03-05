from __future__ import annotations

from dataclasses import dataclass
import os
from typing import List

from app.services.platform_architect_contracts import PLATFORM_ARCHITECT_DOMAIN_TOOLS
from app.services.orchestration_policy_service import (
    ORCHESTRATION_SURFACE_OPTION_B,
    is_orchestration_surface_enabled,
)


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
}

MODEL_REQUIRED_ACTIONS = {
    "agents.create",
    "agents.execute",
    "agents.start_run",
}


def _stable_id(action: str) -> str:
    return action.replace(".", "_")


def _orchestration_expected_block_code() -> str:
    tenant_id = os.getenv("TEST_TENANT_ID")
    enabled = is_orchestration_surface_enabled(
        surface=ORCHESTRATION_SURFACE_OPTION_B,
        tenant_id=tenant_id,
    )
    return "missing_fields" if enabled else "feature_disabled"


def build_scenarios() -> List[ScenarioDefinition]:
    scenarios: list[ScenarioDefinition] = []
    dynamic_expected_block = dict(EXPECTED_BLOCK_BY_ACTION)
    orchestration_code = _orchestration_expected_block_code()
    for action in (
        "orchestration.spawn_run",
        "orchestration.spawn_group",
        "orchestration.join",
        "orchestration.cancel_subtree",
        "orchestration.evaluate_and_replan",
        "orchestration.query_tree",
    ):
        dynamic_expected_block[action] = orchestration_code

    for tool_slug, spec in PLATFORM_ARCHITECT_DOMAIN_TOOLS.items():
        for action in sorted(spec.get("actions", {}).keys()):
            expected_code = dynamic_expected_block.get(action)
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
