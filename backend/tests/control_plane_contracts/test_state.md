Last Updated: 2026-04-14

# Control Plane Contracts Test State

## Scope
Shared control-plane DTO and error contracts.

## Test Files
- `test_control_plane_contracts.py`
- `test_route_adapter_parity.py`

## Scenarios Covered
- Canonical `skip`/`limit`/`view` parsing
- Invalid list-query validation
- Shared list-page envelope serialization: `items`, `total`, `has_more`, `skip`, `limit`, `view`
- Stable control-plane error payload shape
- Canonical operation envelope serialization
- Agents route parity across service, REST adapter, and native tool
- Artifact, orchestration, and RAG route adapters delegate to shared admin services

## Last Run
- Command: `PYTHONPATH=backend python3 -m pytest -q backend/tests/control_plane_contracts/test_control_plane_contracts.py backend/tests/control_plane_contracts/test_route_adapter_parity.py backend/tests/platform_architect_runtime/test_native_platform_assets_actions.py backend/tests/model_registry/test_models_service_parity.py backend/tests/model_registry/test_models_api_contract.py backend/tests/control_plane_sdk/test_client_and_modules.py backend/tests/platform_sdk_tool/test_platform_sdk_sdk_parity.py`
- Date: 2026-04-14
- Result: pass (`52 passed`)

## Known Gaps
- No cross-domain DTO parity coverage yet
