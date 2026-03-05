from app.core.scope_registry import (
    ACTION_REQUIRED_SCOPES,
    ALL_SCOPES,
    PLATFORM_ARCHITECT_SCOPE_PROFILE_V1,
    TENANT_DEFAULT_ROLE_SCOPES,
    build_scope_catalog,
)


def test_action_scope_registry_is_subset_of_all_scopes():
    all_scopes = set(ALL_SCOPES)
    for action, scopes in ACTION_REQUIRED_SCOPES.items():
        for scope in scopes:
            assert scope in all_scopes, f"Missing scope '{scope}' for action '{action}'"


def test_platform_architect_profile_has_model_and_knowledge_store_writes():
    scopes = set(PLATFORM_ARCHITECT_SCOPE_PROFILE_V1)
    assert "models.write" in scopes
    assert "knowledge_stores.write" in scopes


def test_default_roles_include_expected_security_scopes():
    owner_scopes = set(TENANT_DEFAULT_ROLE_SCOPES["owner"])
    admin_scopes = set(TENANT_DEFAULT_ROLE_SCOPES["admin"])
    member_scopes = set(TENANT_DEFAULT_ROLE_SCOPES["member"])

    assert {"roles.read", "roles.write", "roles.assign"}.issubset(owner_scopes)
    assert {"users.read", "users.write", "threads.read", "threads.write"}.issubset(admin_scopes)
    assert "models.write" not in member_scopes
    assert "knowledge_stores.write" not in member_scopes


def test_scope_catalog_contains_groups_and_defaults():
    catalog = build_scope_catalog()
    assert isinstance(catalog.get("groups"), dict)
    assert isinstance(catalog.get("all_scopes"), list)
    assert isinstance(catalog.get("default_roles"), dict)
    assert "agents" in catalog["groups"]
    assert "owner" in catalog["default_roles"]
