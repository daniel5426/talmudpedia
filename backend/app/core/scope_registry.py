from __future__ import annotations

from collections import defaultdict
from typing import Any

# Canonical action -> scope requirements for control-plane actions.
ACTION_REQUIRED_SCOPES: dict[str, list[str]] = {
    "catalog.list_capabilities": ["pipelines.catalog.read"],
    "catalog.get_rag_operator_catalog": ["pipelines.catalog.read"],
    "catalog.list_rag_operators": ["pipelines.catalog.read"],
    "catalog.get_rag_operator": ["pipelines.catalog.read"],
    "catalog.list_agent_operators": ["pipelines.catalog.read"],
    "rag.list_pipelines": ["pipelines.read"],
    "rag.list_visual_pipelines": ["pipelines.read"],
    "rag.operators.catalog": ["pipelines.catalog.read"],
    "rag.operators.schema": ["pipelines.catalog.read"],
    "rag.create_or_update_pipeline": ["pipelines.write"],
    "rag.create_pipeline_shell": ["pipelines.write"],
    "rag.create_visual_pipeline": ["pipelines.write"],
    "rag.update_visual_pipeline": ["pipelines.write"],
    "rag.graph.get": ["pipelines.read"],
    "rag.graph.validate_patch": ["pipelines.write"],
    "rag.graph.apply_patch": ["pipelines.write"],
    "rag.graph.attach_knowledge_store_to_node": ["pipelines.write"],
    "rag.graph.set_pipeline_node_config": ["pipelines.write"],
    "rag.compile_pipeline": ["pipelines.write"],
    "rag.compile_visual_pipeline": ["pipelines.write"],
    "rag.create_job": ["pipelines.write"],
    "rag.get_job": ["pipelines.read"],
    "rag.get_executable_pipeline": ["pipelines.read"],
    "rag.get_executable_input_schema": ["pipelines.read"],
    "rag.get_step_data": ["pipelines.read"],
    "artifacts.list": ["artifacts.read"],
    "artifacts.get": ["artifacts.read"],
    "artifacts.create": ["artifacts.write"],
    "artifacts.update": ["artifacts.write"],
    "artifacts.convert_kind": ["artifacts.write"],
    "artifacts.publish": ["artifacts.publish"],
    "artifacts.delete": ["artifacts.write"],
    "artifacts.create_test_run": ["artifacts.write"],
    "tools.list": ["tools.read"],
    "tools.get": ["tools.read"],
    "tools.create_or_update": ["tools.write"],
    "tools.publish": ["tools.publish"],
    "tools.create_version": ["tools.write"],
    "tools.delete": ["tools.write"],
    "agents.list": ["agents.read"],
    "agents.get": ["agents.read"],
    "agents.create_shell": ["agents.write"],
    "agents.create": ["agents.write"],
    "agents.update": ["agents.write"],
    "agents.create_or_update": ["agents.write"],
    "agents.publish": ["agents.publish"],
    "agents.validate": ["agents.write"],
    "agents.graph.get": ["agents.read"],
    "agents.graph.validate_patch": ["agents.write"],
    "agents.graph.apply_patch": ["agents.write"],
    "agents.graph.add_tool_to_agent_node": ["agents.write"],
    "agents.graph.remove_tool_from_agent_node": ["agents.write"],
    "agents.graph.set_agent_model": ["agents.write"],
    "agents.graph.set_agent_instructions": ["agents.write"],
    "agents.nodes.catalog": ["agents.read"],
    "agents.nodes.schema": ["agents.read"],
    "agents.nodes.validate": ["agents.write"],
    "agents.execute": ["agents.execute"],
    "agents.start_run": ["agents.execute"],
    "agents.resume_run": ["agents.execute"],
    "agents.get_run": ["agents.execute"],
    "agents.get_run_tree": ["agents.execute"],
    "agents.run_tests": ["agents.run_tests"],
    "models.list": ["models.read"],
    "models.create_or_update": ["models.write"],
    "models.add_provider": ["models.write"],
    "models.update_provider": ["models.write"],
    "models.delete_provider": ["models.write"],
    "prompts.list": ["agents.read"],
    "credentials.list": ["credentials.read"],
    "credentials.create_or_update": ["credentials.write"],
    "credentials.delete": ["credentials.write"],
    "credentials.usage": ["credentials.read"],
    "credentials.status": ["credentials.read"],
    "knowledge_stores.list": ["knowledge_stores.read"],
    "knowledge_stores.create_or_update": ["knowledge_stores.write"],
    "knowledge_stores.delete": ["knowledge_stores.write"],
    "knowledge_stores.stats": ["knowledge_stores.read"],
    "api_keys.list": ["api_keys.read"],
    "api_keys.create": ["api_keys.write"],
    "api_keys.revoke": ["api_keys.write"],
    "orchestration.spawn_run": ["agents.execute"],
    "orchestration.spawn_group": ["agents.execute"],
    "orchestration.join": ["agents.execute"],
    "orchestration.cancel_subtree": ["agents.execute"],
    "orchestration.evaluate_and_replan": ["agents.execute"],
    "orchestration.query_tree": ["agents.execute"],
    "respond": [],
}

# Shared scope sets used by control-plane APIs and RBAC.
ORGANIZATION_SCOPES: set[str] = {
    "organizations.read",
    "organizations.write",
    "organization_members.read",
    "organization_members.write",
    "organization_members.delete",
    "organization_invites.read",
    "organization_invites.write",
    "organization_invites.delete",
    "organization_units.read",
    "organization_units.write",
    "organization_units.delete",
    "projects.read",
    "projects.write",
    "projects.archive",
    "roles.read",
    "roles.write",
    "roles.assign",
    "audit.read",
    "stats.read",
    "users.read",
    "users.write",
}

PROJECT_SCOPES: set[str] = {
    scope
    for scopes in ACTION_REQUIRED_SCOPES.values()
    for scope in scopes
}.union(
    {
        "apps.read",
        "apps.write",
        "apps.publish",
        "apps.exposure.write",
        "pipelines.delete",
        "agents.delete",
        "tools.delete",
        "artifacts.delete",
        "threads.read",
        "threads.write",
        "project_settings.read",
        "project_settings.write",
        "project_members.read",
        "project_members.write",
        "project_api_keys.read",
        "project_api_keys.write",
        "api_keys.read",
        "api_keys.write",
        "agents.embed",
        "agents.publish",
        "tools.publish",
        "artifacts.publish",
        "files.read",
        "files.write",
    }
)

ALL_SCOPES: list[str] = sorted(ORGANIZATION_SCOPES.union(PROJECT_SCOPES))

ROLE_FAMILY_ORGANIZATION = "organization"
ROLE_FAMILY_PROJECT = "project"

ORGANIZATION_OWNER_ROLE = "Owner"
ORGANIZATION_READER_ROLE = "Reader"
PROJECT_OWNER_ROLE = "Owner"
PROJECT_MEMBER_ROLE = "Member"
PROJECT_VIEWER_ROLE = "Viewer"

ORGANIZATION_DEFAULT_ROLE_SCOPES: dict[str, list[str]] = {
    ORGANIZATION_OWNER_ROLE: sorted(set(ORGANIZATION_SCOPES)),
    ORGANIZATION_READER_ROLE: sorted({"organizations.read", "projects.read"}),
}

PROJECT_DEFAULT_ROLE_SCOPES: dict[str, list[str]] = {
    PROJECT_OWNER_ROLE: sorted(set(PROJECT_SCOPES).union({"prompts.read", "prompts.write"})),
    PROJECT_MEMBER_ROLE: sorted(
        {
            "apps.read",
            "apps.write",
            "pipelines.catalog.read",
            "pipelines.read",
            "pipelines.write",
            "agents.read",
            "agents.write",
            "agents.execute",
            "agents.run_tests",
            "artifacts.read",
            "artifacts.write",
            "tools.read",
            "tools.write",
            "models.read",
            "knowledge_stores.read",
            "knowledge_stores.write",
            "files.read",
            "files.write",
            "credentials.read",
            "prompts.read",
            "prompts.write",
            "threads.read",
            "threads.write",
        }
    ),
    PROJECT_VIEWER_ROLE: sorted(
        {
            "apps.read",
            "pipelines.catalog.read",
            "pipelines.read",
            "agents.read",
            "artifacts.read",
            "tools.read",
            "models.read",
            "knowledge_stores.read",
            "files.read",
            "credentials.read",
            "threads.read",
        }
    ),
}

CUSTOM_ROLE_ALLOWED_SCOPES: dict[str, set[str]] = {
    ROLE_FAMILY_ORGANIZATION: set(ORGANIZATION_SCOPES),
    ROLE_FAMILY_PROJECT: set(PROJECT_SCOPES).union({"prompts.read", "prompts.write"}),
}

# Legacy export name kept as the active organization-role seed set for code paths
# that have not yet been renamed.
TENANT_DEFAULT_ROLE_SCOPES: dict[str, list[str]] = {
    "owner": list(ORGANIZATION_DEFAULT_ROLE_SCOPES[ORGANIZATION_OWNER_ROLE]),
    "admin": list(ORGANIZATION_DEFAULT_ROLE_SCOPES[ORGANIZATION_OWNER_ROLE]),
    "member": list(ORGANIZATION_DEFAULT_ROLE_SCOPES[ORGANIZATION_READER_ROLE]),
}

# Legacy RBAC migration bridge: existing enum permissions -> canonical scope keys.
LEGACY_PERMISSION_TO_SCOPE: dict[tuple[str, str], str] = {
    ("index", "read"): "pipelines.catalog.read",
    ("index", "write"): "pipelines.write",
    ("index", "delete"): "pipelines.delete",
    ("pipeline", "read"): "pipelines.read",
    ("pipeline", "write"): "pipelines.write",
    ("pipeline", "delete"): "pipelines.delete",
    ("job", "read"): "pipelines.read",
    ("job", "write"): "pipelines.write",
    ("job", "delete"): "pipelines.delete",
    ("organization", "read"): "organizations.read",
    ("organization", "write"): "organizations.write",
    ("organization", "admin"): "organizations.write",
    ("org_unit", "read"): "organization_units.read",
    ("org_unit", "write"): "organization_units.write",
    ("org_unit", "delete"): "organization_units.delete",
    ("role", "read"): "roles.read",
    ("role", "write"): "roles.write",
    ("role", "delete"): "roles.write",
    ("role", "admin"): "roles.assign",
    ("membership", "read"): "organization_members.read",
    ("membership", "write"): "organization_members.write",
    ("membership", "delete"): "organization_members.delete",
    ("audit", "read"): "audit.read",
}


def get_required_scopes_for_action(action: str) -> list[str]:
    return list(ACTION_REQUIRED_SCOPES.get(action, []))


def is_valid_scope(scope: str) -> bool:
    return str(scope or "") in set(ALL_SCOPES)


def normalize_scope_list(scopes: list[str] | tuple[str, ...] | set[str] | None) -> list[str]:
    raw = scopes or []
    cleaned = {str(s).strip() for s in raw if str(s).strip()}
    return sorted(cleaned)


def legacy_permission_to_scope(resource_type: str | None, action: str | None) -> str | None:
    key = (str(resource_type or "").lower(), str(action or "").lower())
    return LEGACY_PERMISSION_TO_SCOPE.get(key)


def build_scope_catalog() -> dict[str, Any]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for scope in ALL_SCOPES:
        prefix = scope.split(".", 1)[0]
        grouped[prefix].append(scope)
    return {
        "groups": {k: sorted(v) for k, v in sorted(grouped.items())},
        "all_scopes": list(ALL_SCOPES),
        "default_roles": {
            "organization": {k: list(v) for k, v in ORGANIZATION_DEFAULT_ROLE_SCOPES.items()},
            "project": {k: list(v) for k, v in PROJECT_DEFAULT_ROLE_SCOPES.items()},
        },
    }


def is_platform_admin_role(role_value: str | None) -> bool:
    return str(role_value or "").strip().lower() in {"admin", "system", "system_admin"}


def allowed_scopes_for_role_family(family: str) -> set[str]:
    return set(CUSTOM_ROLE_ALLOWED_SCOPES.get(str(family or "").strip().lower(), set()))


def preset_role_scopes(*, family: str, name: str) -> list[str]:
    normalized_family = str(family or "").strip().lower()
    normalized_name = str(name or "").strip()
    if normalized_family == ROLE_FAMILY_ORGANIZATION:
        return list(ORGANIZATION_DEFAULT_ROLE_SCOPES.get(normalized_name, []))
    if normalized_family == ROLE_FAMILY_PROJECT:
        return list(PROJECT_DEFAULT_ROLE_SCOPES.get(normalized_name, []))
    return []


def is_preset_role(*, family: str, name: str) -> bool:
    return bool(preset_role_scopes(family=family, name=name))
