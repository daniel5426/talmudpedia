# Model Usage And Cost Accounting Plan

Last Updated: 2026-03-26

Status: Implemented on 2026-03-26. Current behavior now lives in `docs/product-specs/admin_stats_spec.md`.

## Goal

Replace the current approximate token/cost stats flow with a run-accounting architecture that supports any model in the model registry, including hosted, self-hosted, and local models.

Success means:
- token usage is persisted per run with explicit provenance
- cost is computed from the exact provider binding and pricing snapshot used for that run
- stats pages aggregate persisted accounting data instead of reconstructing pricing logic
- unsupported or unknown pricing is represented explicitly as unknown, not faked

## Current Problems

- `GET /admin/stats/summary` sums `AgentRun.usage_tokens` and computes spend using a hardcoded `$0.002 / 1K` formula.
- `AgentRun.usage_tokens` is only a single aggregate integer.
- usage falls back to a rough `chars / 4` estimate when provider usage is unavailable.
- the model registry stores pricing on `ModelProviderBinding`, but stats do not use it.
- runs store `resolved_model_id` but not the exact resolved provider binding.
- historical cost cannot be reconstructed safely if registry pricing changes later.
- local/self-hosted models have no first-class accounting contract today.

## Design Principles

- usage accounting is a runtime concern, not a dashboard concern
- logical model selection and billing identity must be separate
- exact observed usage beats estimation
- explicit `unknown` beats fake precision
- historical runs must keep a pricing snapshot
- pricing rules must live on provider bindings, not logical models
- stats should aggregate accounting facts, not infer them

## Target State

Each run will persist:
- which logical model was requested
- which exact provider binding executed
- normalized usage metrics with provenance
- pricing snapshot used at execution time
- computed cost with provenance

Each stats view will show:
- exact token totals
- estimated token totals
- unknown token coverage
- exact spend totals
- estimated spend totals if intentionally allowed
- unknown spend coverage

## Slice 1: Canonical Accounting Contract

Define a backend-internal normalized accounting shape for model execution.

Recommended contract:
- `usage_source`
  - `provider_reported`
  - `sdk_reported`
  - `estimated`
  - `unknown`
- `cost_source`
  - `binding_pricing`
  - `provider_reported`
  - `manual_override`
  - `unknown`
- `NormalizedUsage`
  - `input_tokens`
  - `output_tokens`
  - `total_tokens`
  - `cached_input_tokens`
  - `cached_output_tokens`
  - `reasoning_tokens`
  - `audio_input_tokens`
  - `audio_output_tokens`
  - `image_input_units`
  - `image_output_units`
  - `extra`
- `NormalizedCost`
  - `currency`
  - `total_cost`
  - `line_items`
  - `source`

Notes:
- `total_tokens` should be nullable, not forced, because some providers expose partial metrics only.
- `extra` and `line_items` should remain extensible for provider-specific billable dimensions.

Deliverables:
- new accounting types module
- explicit invariants for exact vs estimated vs unknown
- small helper layer for rollup-friendly totals

## Slice 2: Run Schema Upgrade

Extend `AgentRun` so accounting is persisted as first-class data.

Add fields:
- `resolved_binding_id`
- `resolved_provider`
- `resolved_provider_model_id`
- `usage_source`
- `cost_source`
- `input_tokens`
- `output_tokens`
- `total_tokens`
- `cached_input_tokens`
- `cached_output_tokens`
- `reasoning_tokens`
- `usage_breakdown_json`
- `cost_usd`
- `cost_breakdown_json`
- `pricing_snapshot_json`

Keep for compatibility:
- `usage_tokens`
- existing `cost` string field until callers are migrated

Rules:
- `usage_tokens` becomes a legacy mirror of `total_tokens` when known
- `cost` string should stop being authoritative
- new queries and stats should read the structured fields

Migration strategy:
- do not attempt fake historical backfill
- optionally copy `usage_tokens -> total_tokens` for legacy rows and mark them `estimated` or `legacy_unknown`
- leave `cost_usd` null for old rows

Deliverables:
- Alembic migration
- updated SQLAlchemy model
- compatibility notes for old consumers

## Slice 3: Resolution Receipt

Change model resolution so it returns a stable execution receipt instead of only a provider instance.

Required receipt fields:
- logical model id
- resolved binding id
- provider
- provider model id
- tenant/global binding scope
- pricing config
- pricing version or snapshot source
- capability flags

Capability flags:
- `supports_usage_reporting`
- `supports_stream_usage`
- `supports_final_usage_reporting`
- `supports_provider_cost_reporting`
- `supports_separate_input_output_tokens`

Reason:
- billing needs the exact binding identity
- stats and audits need a stable execution record
- the same logical model may route to different providers

Deliverables:
- resolver return-type refactor
- run creation path updated to persist resolved binding identity immediately

## Slice 4: Usage Extraction Pipeline

Create a provider-agnostic extraction path that gathers usage from all available sources in priority order.

Priority order:
1. provider/native final usage payload
2. provider/native streaming usage payload
3. SDK or LangChain normalized usage metadata
4. explicit adapter-provided usage object
5. estimator fallback
6. unknown

Requirements:
- extract usage from final response objects when present
- extract usage from streaming chunks when present
- normalize LangChain usage metadata into the internal contract
- avoid double counting when both stream and final usage are emitted
- persist provenance for every run

Important policy:
- estimation must be opt-in within the accounting service, not hidden in the stats layer
- estimated usage must always be marked as estimated

Deliverables:
- `usage_normalizer` service
- adapter hooks for current LangChain-backed providers
- tests for exact vs estimated precedence

## Slice 5: Pricing Engine

Introduce a dedicated pricing engine service.

Inputs:
- normalized usage
- resolved binding
- pricing snapshot
- optional provider-reported cost

Outputs:
- `cost_usd`
- structured cost breakdown
- provenance

Pricing source precedence:
1. binding pricing snapshot
2. trusted provider-reported cost if supported and enabled
3. manual override pricing
4. unknown

Requirements:
- pricing must be computed at run finalization time
- pricing snapshot must be stored on the run
- historical totals must not change if registry pricing changes later
- zero-cost local models must be representable explicitly
- unknown-cost runs must remain queryable and visible

Deliverables:
- `run_cost_engine` service
- pricing snapshot serializer
- exact line-item calculator

## Slice 6: Registry Pricing Contract Upgrade

Upgrade the pricing model on `ModelProviderBinding`.

Current fields:
- `cost_per_1k_input_tokens`
- `cost_per_1k_output_tokens`

Target:
- keep current fields only as a short-term compatibility layer
- add structured pricing config JSON

Suggested pricing config shape:
- `currency`
- `billing_mode`
  - `per_token`
  - `per_1k_tokens`
  - `flat_per_request`
  - `manual`
  - `unknown`
- `rates`
  - input
  - output
  - cached_input
  - cached_output
  - reasoning
  - audio_input
  - audio_output
  - image_input
  - image_output
- `minimum_charge`
- `effective_from`
- `pricing_version`

Reason:
- arbitrary providers and local models need a richer contract than input/output only
- future providers may price cache, reasoning, or multimodal units differently

Deliverables:
- model binding schema update
- validation rules in models API
- admin UI follow-up for binding pricing editing

## Slice 7: Runtime Finalization Rewrite

Move all accounting writes into a single finalization path.

At run finalization:
- resolve best observed usage
- normalize usage
- compute pricing snapshot
- compute final cost
- persist structured accounting
- mirror compatibility fields if still needed

Rules:
- accounting must happen once per run
- paused and failed runs should still persist partial accounting when available
- if usage is unknown, keep cost unknown unless a flat request charge is defined

Deliverables:
- refactor execution service finalization
- central helper for both success and failure paths
- idempotent finalization behavior

## Slice 8: Stats Contract Rewrite

Rewrite admin stats to aggregate accounting facts only.

Overview and agent stats should aggregate:
- `total_tokens_exact`
- `total_tokens_estimated`
- `runs_with_unknown_usage`
- `total_spend_exact_usd`
- `runs_with_unknown_cost`
- optional breakdowns by provider, model, binding, and provenance

UI rules:
- if cost includes unknown rows, show that explicitly
- if tokens include estimated rows, show that explicitly
- do not show a single precise spend number when coverage is partial unless the UI labels it clearly

Required backend changes:
- remove hardcoded spend math from stats router
- replace it with structured aggregation over new run accounting fields

Deliverables:
- stats schema update
- stats router update
- frontend stats labels for exact vs estimated vs unknown

## Slice 9: Provider Rollout Order

Implement in this order:

1. OpenAI
- strong baseline for input/output token reporting
- easy validation path

2. Anthropic
- validate separate usage mapping and reasoning/cached-token behavior if available

3. Gemini
- validate normalized usage coverage through current adapter path

4. xAI
- validate compatibility through the existing OpenAI-style integration path

5. Local/self-hosted
- support explicit registry-declared pricing
- support exact usage if adapter provides it
- support unknown usage/cost when provider cannot report it

Deliverables:
- provider-specific mapping tests
- support matrix doc or inline reference table

## Slice 10: Backfill And Compatibility

Handle old data without pretending it is exact.

Backfill rules:
- legacy rows with only `usage_tokens` become `total_tokens`
- mark legacy rows as `estimated` or `legacy_unknown`
- leave `cost_usd` null unless a deliberate historical migration is approved

Compatibility period:
- old endpoints can continue returning `usage_tokens`
- old spend displays should either:
  - be migrated immediately, or
  - be labeled as legacy/approximate until removed

Deliverables:
- one-time data migration decision
- compatibility window defined before cleanup

## Slice 11: Testing

Create feature-grouped tests under `backend/tests/`.

Suggested test directories:
- `backend/tests/model_accounting/`
- `backend/tests/admin_stats_accounting/`

Required coverage:
- exact provider usage persisted
- final response usage beats estimator
- stream usage and final usage do not double count
- unknown usage stays unknown
- local model with manual pricing computes cost correctly
- pricing snapshot protects historical runs from registry edits
- stats aggregation separates exact vs estimated vs unknown
- failed and paused runs persist partial accounting correctly

Also add:
- `test_state.md` in each new feature test directory

## Slice 12: Cleanup

After all callers migrate:
- stop using `usage_tokens` as the primary source
- stop using the string `cost` field
- remove hardcoded spend formulas
- remove any dashboard approximation logic that hides provenance

Optional follow-up:
- expose accounting drilldown per run in admin thread/run details
- add per-binding/provider spend reporting
- add coverage metrics for exact vs estimated accounting by provider

## Recommended Execution Order

1. Slice 1: canonical accounting contract
2. Slice 2: run schema upgrade
3. Slice 3: resolution receipt
4. Slice 4: usage extraction pipeline
5. Slice 5: pricing engine
6. Slice 7: runtime finalization rewrite
7. Slice 8: stats contract rewrite
8. Slice 9: provider rollout order
9. Slice 11: testing
10. Slice 10: backfill and compatibility
11. Slice 12: cleanup
12. Slice 6: registry pricing contract upgrade if not needed earlier for MVP

## MVP Cut

If we want the smallest useful delivery:
- add structured run accounting fields
- persist resolved binding id
- extract exact usage for OpenAI, Anthropic, and Gemini when available
- compute cost from current binding pricing fields
- mark unsupported/local models as unknown or estimated
- update stats to stop using the hardcoded spend constant

This MVP already removes the current fake pricing problem while keeping room for richer provider support later.

## Open Decisions

- whether `usage_tokens` should remain a physical column long term
- whether `cost_usd` should be nullable or default to `0`
- whether provider-reported cost should ever override binding pricing
- whether estimation should be enabled by default for local models
- whether pricing config migration should happen before or after the first accounting MVP

## Canonical Implementation References

- `backend/app/api/routers/stats.py`
- `backend/app/agent/execution/service.py`
- `backend/app/services/model_resolver.py`
- `backend/app/db/postgres/models/agents.py`
- `backend/app/db/postgres/models/registry.py`
