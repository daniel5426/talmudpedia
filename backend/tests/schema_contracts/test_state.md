# Schema Contract Surface Tests

Last Updated: 2026-04-22

## Scope
- Contract surfaces that teach the architect the exact create-time wrapper shape for RAG operators and agent graph nodes.
- Regression coverage for richer schema responses beyond basic config metadata.

## Test files present
- test_schema_contract_surfaces.py

## Key scenarios covered
- `rag.operators.schema` exposes config schema plus canonical `node_template`, `normalization_defaults`, shared pipeline instance contract details, and preserved numeric/JSON/runtime field constraints.
- `rag.operators.schema` now excludes runtime-only fields from authoring-required catalog hints, removes stale `org_unit_id` from the canonical pipeline wrapper contract, and exposes union-shaped config like `web_crawler.start_urls` when the runtime accepts multiple input forms.
- `agents.nodes.schema` exposes per-node graph wrapper contract plus canonical `node_template`, `normalization_defaults`, and richer shared graph instance contract details.
- Artifact-backed agent nodes and custom RAG operators use the same enriched schema shape as built-in nodes/operators.

## Last run command + date/time + result
- Command: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest -q backend/tests/schema_contracts/test_schema_contract_surfaces.py`
- Date/Time: 2026-04-22 Asia/Hebron
- Result: passed (`5 passed`)
- Command: `SECRET_KEY=explicit-test-secret backend/.venv/bin/python -m pytest -q backend/tests/schema_contracts/test_schema_contract_surfaces.py backend/tests/platform_architect_runtime/test_architect_seeding.py backend/tests/platform_architect_runtime/test_native_platform_tools.py`
- Date/Time: 2026-04-22 Asia/Hebron
- Result: passed (`32 passed, 6 warnings`)

## Known gaps or follow-ups
- Add integration coverage that exercises the live HTTP routes and Platform SDK action envelopes for these enriched schema responses.
