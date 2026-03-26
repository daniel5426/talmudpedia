# Execution Plan: Resource Policy Sets Full Test Plan

Last Updated: 2026-03-26

## Status: Active

This plan defines the full test inventory for the new resource policy sets domain.

The goal is not just smoke coverage. The goal is to prove:
- policy-set persistence is correct
- assignment/default resolution is correct
- runtime enforcement is correct at every protected boundary
- quota settlement stays aligned with canonical model accounting
- admin API behavior is correct
- frontend admin UX is correctly wired to the backend contract
- the new domain does not regress existing workload-delegation and execution behavior

## Canonical Scope

This plan covers the resource-policy-set MVP introduced across:
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/db/postgres/models/resource_policies.py`
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/services/resource_policy_service.py`
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/services/resource_policy_quota_service.py`
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/api/routers/resource_policies.py`
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/agent/execution/service.py`
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/services/model_resolver.py`
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/services/retrieval_service.py`
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/agent/executors/tool.py`
- `/Users/danielbenassaya/Code/personal/talmudpedia/backend/alembic/versions/d4e5f6a7b8c9_add_resource_policy_sets.py`

It also covers the admin frontend for the same domain once the UI lands.

## MVP Domain Contract To Lock Down

These are the exact semantics the tests must enforce:

1. A policy set is the single assignable object.
2. Policy sets may include other policy sets.
3. Include cycles are invalid.
4. Rule types are limited to:
- `allow`
- `quota`

5. Resource types are limited to:
- `agent`
- `tool`
- `knowledge_store`
- `model`

6. Quotas are MVP-limited to model token quotas only.
7. Quota unit is `tokens`.
8. Quota window is `monthly`.
9. There is one direct policy-set assignment per principal.
10. Principal types are:
- `tenant_user`
- `published_app_account`
- `embedded_external_user`

11. Embedded external identity is keyed by:
- `embedded_agent_id + external_user_id`

12. Published apps can have a default policy set.
13. Embedded/public agents can have a default policy set.
14. Direct assignment overrides defaults.
15. Snapshot resolves once at run start and is reused for nested calls.
16. Early filtering is out of scope for MVP.
17. Enforcement is deny-on-use at protected resource boundaries.
18. Model quota settlement must use canonical persisted run accounting, especially `total_tokens` / model-accounting fallback semantics.
19. Normal user-created agents must no longer require workload approval/delegation just to run.
20. Internal privileged workload paths must continue to work.

## Test Strategy

We need five layers:

1. Migration tests
- prove schema shape is correct on real Postgres

2. Unit/service tests
- prove isolated policy resolution and quota behavior

3. API contract tests
- prove CRUD, validation, authz, and error behavior of the new router

4. Runtime integration tests
- prove actual execution-path enforcement for agents, tools, retrieval, nested calls, and model quotas

5. Frontend/admin tests
- prove the UI consumes and mutates the backend correctly

Do not rely on only one layer. This domain spans persistence, control-plane APIs, runtime enforcement, and admin UX.

## Test Roots And Organization

Backend:
- create or expand `/Users/danielbenassaya/Code/personal/talmudpedia/backend/tests/resource_policy_sets/`
- keep tests grouped by feature, not by code file
- maintain `/Users/danielbenassaya/Code/personal/talmudpedia/backend/tests/resource_policy_sets/test_state.md`

Frontend:
- create `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/__tests__/resource_policy_sets/`
- maintain `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/__tests__/resource_policy_sets/test_state.md`

Recommended backend file split:
- `test_policy_set_model_and_resolution.py`
- `test_policy_set_admin_api.py`
- `test_policy_set_runtime_enforcement.py`
- `test_policy_set_quota_accounting.py`
- `test_policy_set_migration_real_db.py`

Recommended frontend file split:
- `resource_policy_sets_page.test.tsx`
- `resource_policy_sets_service.test.ts`

## Environment Split

Some tests are safe on SQLite/in-memory.
Some tests must run on real Postgres.
Some advanced integration tests may and should use real platform resources when that is the thing being validated.

### SQLite-Safe
- pure service logic
- snapshot resolution
- most router behavior
- most frontend tests

### Real Postgres Required
- migration correctness
- enum creation/drop behavior
- partial unique indexes
- conflict behavior that depends on real Postgres uniqueness/index semantics
- any test that validates Alembic upgrade/downgrade behavior

### Live Resource / Real Provider Lane
- a dedicated opt-in integration lane should be allowed to use real platform-wired resources when required
- this includes real model bindings, real provider credentials, real knowledge stores, and other real tenant resources if the scenario under test actually depends on them
- these tests should use the same environment/profile loading path as the backend application
- they should use the existing local env vars and tenant/provider wiring already configured for the platform, rather than inventing parallel test-only credential paths
- if the local environment is wired to the operator's real account/provider setup, that is acceptable and expected for this lane
- these tests must be clearly separated from the deterministic/default suite
- these tests should fail clearly when required local env vars, credentials, or tenant resources are missing
- these tests should not silently downgrade to mocks if the purpose of the test is real integration verification

### Explicit Rule
- the test plan does not forbid real resource usage
- the only rule is that the suite must make the lane explicit:
  - deterministic lane for stable default coverage
  - live integration lane for real platform/resource verification

Mark real-DB tests explicitly and keep them separate.

## Required Fixture Inventory

Create reusable fixtures/helpers for:
- tenant
- internal user
- org unit + membership
- agent
- published app
- published app account
- embedded agent
- model row
- tool row
- knowledge store row
- policy set
- policy rule
- policy include edge
- policy assignment
- agent run with controlled accounting fields

Also add fixtures for principal contexts:
- tenant user principal
- published app account principal
- embedded external principal

And runtime contexts:
- normal internal run
- published app run
- embedded run
- nested agent-call run

## Suite 1: Migration Coverage

### Goal
Prove the schema is deployable and reversible on real Postgres.

### Cases
- upgrade from previous head to `d4e5f6a7b8c9`
- all new tables exist after upgrade
- new columns exist on:
  - `published_apps.default_policy_set_id`
  - `agents.default_embed_policy_set_id`
  - `agent_runs.external_user_id`
- all expected foreign keys exist
- all expected indexes exist
- all expected enum types exist
- downgrade removes the new tables, columns, indexes, and enum types cleanly
- rerunning upgrade after a failed partial attempt is safe
- enum creation does not fail with duplicate-object errors

### Important Edge Cases
- partial unique indexes for assignments
- enum lifecycle under transactional migrations
- downgrade after upgrade on a non-empty test dataset

## Suite 2: Model And Resolution Service Coverage

### Goal
Prove snapshot construction and principal/default/override semantics.

### Cases
- resolve snapshot for `tenant_user` direct assignment
- resolve snapshot for `published_app_account` default policy set
- resolve snapshot for `embedded_external_user` default policy set
- direct assignment overrides default for published app account
- no assignment + no default returns `None`
- nested includes flatten correctly
- include cycles are rejected
- self-include is rejected
- included policy set from another tenant is rejected
- inactive policy set behavior is explicit and tested
- snapshot payload round-trip works
- multiple allow rules across included sets merge correctly
- multiple quota rules across included sets for different models merge correctly
- conflicting quota rules for the same model are rejected
- quota rule on non-model resource is rejected
- non-monthly quota window is rejected
- non-token quota unit is rejected
- non-positive quota limit is rejected

### Important Behavioral Assertions
- only resource types with explicit allow rules become restricted in the snapshot
- unrestricted resource types remain allowed
- direct-assignment override does not merge with defaults unless the backend explicitly does so

## Suite 3: Admin API Coverage

### Goal
Prove the router is complete, correct, and secure.

### Policy Set CRUD
- list sets
- get set
- create set
- update set
- delete set
- duplicate name in same tenant returns conflict
- same name across different tenants is allowed if intended by schema
- user principal required
- `roles.read` required for reads
- `roles.write` required for writes

### Include Management
- add include
- remove include
- add include across tenants fails
- add include that creates cycle fails
- duplicate include edge fails cleanly
- removing missing include returns 404

### Rule Management
- create allow rule for each resource type
- create quota rule for model
- reject quota rule for non-model resource
- reject invalid quota limit/unit/window
- update quota rule
- update allow rule `resource_id`
- duplicate conflicting rules return conflict
- delete rule
- delete missing rule returns 404

### Assignment Management
- list assignments
- create tenant-user assignment
- create published-app-account assignment
- create embedded-external-user assignment
- upsert changes policy set for existing principal
- reject missing principal identifiers
- enforce one direct assignment per principal
- delete assignment for each principal type
- deleting missing assignment returns 404
- cross-tenant references are rejected

### Default Policy Set Management
- set published app default
- clear published app default with `null`
- set embedded agent default
- clear embedded agent default with `null`
- reject foreign-tenant policy set
- reject missing app/agent

### Error Contract Coverage
- 400 validation failures
- 403 permission failures
- 404 missing objects
- 409 duplicate/conflict failures

## Suite 4: Runtime Enforcement Coverage

### Goal
Prove actual runtime boundaries are enforced, not just service helpers.

### Agent Start
- user with no policy set can start a normal default agent
- first run for a new user no longer requires workload delegation
- user with direct policy set that excludes the target agent is denied at run start
- published app account denied when agent is restricted
- embedded external user denied when agent is restricted
- direct assignment override behavior is preserved at run start
- snapshot is attached to run context

### Tool Boundary
- allowed tool executes
- restricted tool is denied at invocation time
- inactive tool still denied independently of policy set
- nested agent call inherits snapshot/principal context correctly
- child run uses frozen parent snapshot instead of re-resolving mid-run

### Knowledge Store Boundary
- allowed knowledge store retrieval succeeds
- restricted knowledge store retrieval is denied even when:
  - agent is allowed
  - tool is allowed
- multi-store query returns allowed stores and rejects restricted stores according to current backend behavior
- embedded and published-app contexts enforce the same knowledge-store guard

### Model Boundary
- allowed model resolves successfully
- restricted model is denied before invocation
- embedding model used inside retrieval is also checked
- standard agent node model resolution honors snapshot
- classify node model resolution honors snapshot
- accounting receipt resolution path honors snapshot

### Nested Call Chains
- agent -> tool -> knowledge store
- agent -> tool -> model
- agent -> agent -> tool
- parent allowed but child agent restricted
- parent allowed and child allowed but child tool restricted
- parent run snapshot remains stable even if assignment changes during execution

### Important Edge Cases
- malformed `resource_policy_snapshot` payload in context
- malformed principal payload in context
- missing context should fall back to fresh resolution for top-level runs
- internal coding-agent surfaces still keep workload delegation requirements
- normal agent surfaces must not regress back into workload-grant requirement

### Live Integration Variants
- at least one variant of the runtime suite should run against a real resolved model/provider path using the platform's normal env-backed credential flow
- at least one quota scenario should be validated with a real model invocation so canonical usage settlement is proven with real provider/runtime behavior, not only synthetic runs
- at least one nested scenario should be validated with real platform-wired resources where practical

## Suite 5: Quota Accounting Coverage

### Goal
Prove quota reservation and settlement are correct and aligned with model-usage spec.

### Reservation
- no snapshot -> no-op
- no principal -> no-op
- no model quota for requested model -> no-op
- quota reservation succeeds within limit
- quota reservation fails when projected usage exceeds limit
- reservation creates/updates the correct monthly counter
- multiple reservations in same month accumulate reserved tokens
- different principals do not share counters
- different models do not share counters

### Settlement
- settlement uses canonical `billable_total_tokens(run)`
- `total_tokens` is preferred over legacy `usage_tokens`
- reservation settlement decrements `reserved_tokens`
- settlement increments `used_tokens`
- settling a run with no reservation is a no-op
- settling a run with no resolved model is a no-op
- repeated settlement behavior is explicitly tested and locked down

### Cross-Run Behavior
- assignment changes affect the next run, not the current one
- quota counters roll up within same monthly window
- a new monthly window starts a fresh counter

### Failure/Recovery Cases
- failed run still settles quota using persisted accounting
- partial run with canonical totals still settles correctly
- legacy accounting fallback remains consistent with `model_usage_spec.md`

### Live Integration Variant
- include at least one live-provider quota test using the platform's normal env/config wiring
- this test should explicitly rely on existing backend env vars and credential resolution, not an alternate test-only path
- the purpose is to prove that real usage emitted by a real provider path still settles correctly into policy-set quota accounting

## Suite 6: Regression Coverage Against Existing Domains

### Goal
Ensure the new domain does not silently break unrelated paths.

### Required Regressions
- existing workload-delegation tests still pass
- internal coding-agent flows still run
- platform architect privileged path still runs
- existing model accounting tests still pass
- existing model registry tests still pass
- existing embedded runtime auth resolution still passes
- existing published app runtime auth resolution still passes

### Minimum Regression Commands
- resource-policy-set backend suite
- existing workload delegation/auth suites
- model accounting suite
- model registry suite
- embedded runtime relevant suite
- published app runtime relevant suite

## Suite 7: Frontend Service Coverage

### Goal
Prove the frontend service layer matches the backend contract exactly.

### Cases
- list/get/create/update/delete policy set
- add/remove include
- create/update/delete rule
- list/upsert/delete assignment
- set/clear published app default
- set/clear embedded agent default
- request/response typing matches backend payloads
- error propagation is clean

### Important Assertions
- shared types live only under `frontend-reshet/src/services/`
- `frontend-reshet/src/services/index.ts` exports are correct
- no page-local API clients or duplicate types were introduced

## Suite 8: Frontend Admin UI Coverage

### Goal
Prove the admin UI is functional end-to-end.

### Cases
- initial page load fetches policy sets and/or assignments correctly
- create policy set flow works
- edit policy set flow works
- delete policy set flow works
- include add/remove flow works
- rule create flow for allow rules works
- rule create flow for model quota works
- invalid rule submission surfaces backend error
- assignment creation flow for each principal type works
- assignment update/upsert flow works
- assignment delete flow works
- set/clear published app default works
- set/clear embedded agent default works
- loading states are shown
- empty states are shown
- mutation success refreshes visible data
- permission failures are surfaced clearly
- backend validation/conflict errors are surfaced clearly

### Frontend Edge Cases
- empty policy-set list
- empty assignments list
- stale/deleted target object during edit
- duplicate-name conflict
- include-cycle failure
- conflicting rule failure
- assignment delete of already-removed row

## Scenario Matrix That Must Exist

At least one test each for:
- internal user + direct assignment
- internal user + no assignment
- published app account + default only
- published app account + direct assignment override
- embedded external user + default only
- embedded external user + direct assignment override if later supported
- agent allow restriction
- tool allow restriction
- knowledge store allow restriction
- model allow restriction
- model quota restriction
- nested included policy sets
- conflict rejection
- runtime nested call enforcement

## Prioritized Implementation Order

### Phase 1
- migration real-DB coverage
- service/model resolution coverage
- quota accounting coverage

### Phase 2
- admin API CRUD and authz coverage
- runtime enforcement coverage on agent/tool/model/knowledge-store boundaries

### Phase 3
- nested execution-path coverage
- regression suite expansion

### Phase 4
- frontend service tests
- frontend admin UI tests

## Minimum Acceptance Bar

Before this domain is considered fully tested:

1. All migration tests pass on real Postgres.
2. Service/API/runtime coverage exists for every principal type.
3. Every protected resource type has both allow and deny-path tests.
4. Quota logic is proven against canonical accounting semantics.
5. Direct assignment override and default resolution are both covered.
6. Nested-call enforcement is covered.
7. Frontend service and UI flows are covered.
8. `test_state.md` files are updated with the real last-run commands/results.

## Explicit Non-Goals For This Test Plan

Do not spend time on:
- deny-rule behavior, because deny rules do not exist in MVP
- extra quota units or windows, because they do not exist in MVP
- speculative policy language extensions
- early-filtering behavior, because it is intentionally out of scope

## Implementation Notes For The Follow-Up Agent

- Start by expanding the current seed tests in `/Users/danielbenassaya/Code/personal/talmudpedia/backend/tests/resource_policy_sets/`
- Add real-DB migration tests separately and mark them accordingly
- Reuse fixtures aggressively
- Keep each test file focused on behavior, not code-file ownership
- Update backend and frontend `test_state.md` files as suites are added
- If any backend/frontend contract drift is discovered while implementing tests, stop and record it explicitly instead of silently adapting the tests
- Make the live integration lane explicit in naming, markers, and run commands
- For live integration tests, load env/config exactly as the backend does and rely on the existing local provider wiring when present
