# Schema Contract Surface Tests

Last Updated: 2026-03-08

## Scope
- Contract surfaces that teach the architect the exact create-time wrapper shape for RAG operators and agent graph nodes.
- Regression coverage for richer schema responses beyond basic config metadata.

## Test files present
- test_schema_contract_surfaces.py

## Key scenarios covered
- `rag.operators.schema` exposes config schema, runtime-binding-aware field contracts, visual node contract, and shared pipeline create contract details.
- `agents.nodes.schema` exposes per-node graph wrapper contract and shared graph create contract details.

## Last run command + date/time + result
- Command: `cd backend && pytest -q tests/schema_contracts/test_schema_contract_surfaces.py tests/platform_architect_runtime/test_architect_seeding.py tests/platform_sdk_tool/test_platform_sdk_actions.py tests/platform_sdk_tool/test_platform_sdk_sdk_parity_additional_actions.py`
- Date/Time: 2026-03-08
- Result: passed (`83 passed, 5 warnings`)

## Known gaps or follow-ups
- Add integration coverage that exercises the live HTTP routes and Platform SDK action envelopes for these enriched schema responses.
