# Tenant API Keys Tests

Last Updated: 2026-03-16

Scope:
- Tenant-scoped API-key admin routes for create, list, and revoke.
- Secret visibility guarantees for API-key creation flows.

Test files present:
- test_api_keys_api.py

Key scenarios covered:
- Create returns bearer token material once alongside stored key metadata.
- List returns stored metadata without replaying secret material.
- Revoke transitions key status to `revoked`.

Last run command: `cd backend && PYTHONPATH=. pytest -q tests/tenant_api_keys/test_api_keys_api.py tests/embedded_agent_runtime/test_embedded_agent_runtime_api.py tests/control_plane_sdk tests/published_apps_external_runtime/test_external_runtime_api.py tests/published_apps_host_runtime/test_host_runtime_same_url_auth.py tests/security_scope_registry/test_scope_registry.py`
Last run date/time: 2026-03-16 19:38 EET
Last run result: pass (`45 passed, 2 skipped`)

Known gaps / follow-ups:
- Add admin authorization failure coverage for missing `api_keys.*` scopes if those routes broaden beyond owner/admin defaults.
