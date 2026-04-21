# Test State: Runtime Surface Standardization

Last Updated: 2026-04-21

**Scope**
Shared runtime-surface facade coverage for internal agent routes, published runtime routes, and embedded runtime routes.

**Test Files**
- `test_runtime_surface_routes.py`

**Scenarios Covered**
- New run start/stream headers across internal, published external, and embedded surfaces.
- Paused run resume payload handling across internal and published external surfaces.
- Internal run-event history remains full-fidelity and tenant-guarded.
- Internal cancel keeps the existing terminal payload shape and persists partial assistant output.
- Host runtime thread detail now exercises the canonical runtime-surface public event projection path.
- Public-safe thread-history event envelopes stay aligned between published external and embedded thread detail.

**Last Run**
- Command: `SECRET_KEY=test-secret-key PYTHONPATH=backend backend/.venv/bin/pytest -q backend/tests/runtime_surface_standardization/test_runtime_surface_routes.py`
- Date: 2026-04-21 Asia/Hebron
- Result: PASS (`5 passed`)

**Known Gaps / Follow-ups**
- No dedicated host-runtime cookie-path regression test in this feature slice; existing `published_apps_host_runtime` tests still cover that surface.
- No route-level subthread regression here; existing embedded/published/admin thread-detail suites remain the main coverage for subtree expansion.
