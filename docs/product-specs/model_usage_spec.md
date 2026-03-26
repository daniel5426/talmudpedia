# Model Usage Spec

Last Updated: 2026-03-26

This document is the canonical product/specification overview for persisted model-usage and cost accounting.

## Purpose

Define the canonical backend contract for:
- per-run model usage accounting
- per-run model cost accounting
- pricing snapshot persistence
- exact vs estimated vs unknown provenance

## Scope

This spec covers persisted accounting on agent runs.

It does not define:
- frontend presentation details beyond the shared accounting fields
- provider-specific SDK quirks
- quota reservation heuristics before a run starts

## Canonical Runtime Facts

Each run may persist:
- `requested_model_id`
- `resolved_model_id`
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

Legacy compatibility fields still present:
- `usage_tokens`
- `cost`

## Provenance Contract

### Usage Sources

Canonical usage provenance values:
- `provider_reported`
- `sdk_reported`
- `estimated`
- `unknown`
- `legacy_estimated`
- `legacy_unknown`

Meaning:
- provider-reported means the provider exposed usage directly
- sdk-reported means normalized SDK metadata supplied the usage
- estimated means the runtime intentionally computed an estimate
- unknown means the runtime did not observe usable usage data

### Cost Sources

Canonical cost provenance values:
- `binding_pricing`
- `provider_reported`
- `manual_override`
- `unknown`

Meaning:
- binding-pricing means cost was computed from the persisted pricing snapshot
- provider-reported means a trusted provider total was accepted directly
- manual-override means the pricing snapshot explicitly used manual pricing
- unknown means the run cannot be priced safely

## Usage Rules

- Usage accounting is a runtime concern, not a dashboard concern.
- `total_tokens` is the canonical token total when present.
- `usage_tokens` is a legacy compatibility mirror of `total_tokens`.
- Exact usage must never be downgraded to an estimate.
- Estimated usage must remain explicitly labeled as estimated.
- Unknown usage must remain unknown instead of being replaced with fake precision.

## Pricing Rules

- Pricing is bound to the resolved provider binding, not just the logical model.
- Each priced run must persist the pricing snapshot used at execution time.
- Historical runs must not change if current registry pricing changes later.
- Local or self-hosted models may be explicitly zero-cost.
- If usage is unknown and pricing needs usage dimensions, cost must stay unknown.

## Pricing Snapshot Contract

Current snapshot shape supports:
- `currency`
- `billing_mode`
- `rates`
- `minimum_charge`
- `manual_total_cost`
- `flat_amount`

Supported billing modes:
- `per_token`
- `per_1k_tokens`
- `flat_per_request`
- `manual`
- `unknown`

## Aggregation Contract

Shared accounting rollups may expose:
- `total_tokens`
- `total_tokens_exact`
- `total_tokens_estimated`
- `runs_with_unknown_usage`
- `estimated_spend_usd`
- `total_spend_exact_usd`
- `total_spend_estimated_usd`
- `runs_with_unknown_cost`

Rollup rules:
- total tokens include persisted `total_tokens` with legacy `usage_tokens` as fallback
- exact token totals include `provider_reported` and `sdk_reported`
- estimated token totals include explicit estimated rows only
- spend totals aggregate persisted `cost_usd`
- unknown coverage is reported as row counts, not imputed values

## Registry Pricing Contract

`model_provider_bindings.pricing_config` is now the canonical pricing source for new and updated bindings.

Current write-path rules:
- registry create/update APIs accept `pricing_config` only for `custom` and `local`
- built-in provider bindings use platform-managed pricing from the global registry seed/catalog layer
- global seeded bindings are the canonical pricing source for built-in provider spend accounting
- registry create/update APIs do not accept `billing_mode=manual`
- registry create/update APIs reject tenant pricing for platform-managed providers
- runtime pricing reads only `pricing_config`
- empty `pricing_config` means the run remains unpriced unless another explicit pricing source exists

Internal-only note:
- `manual_total_cost` remains available only for internal override snapshots, not tenant-managed registry editing

Registry ownership rules:
- built-in providers such as `openai`, `anthropic`, `google`, and `xai` are platform-priced
- `custom` and `local` providers are tenant-priced
- global seeded models remain visible in the registry but are read-only for tenants

Legacy fields still on the table but no longer used by runtime pricing:
- `cost_per_1k_input_tokens`
- `cost_per_1k_output_tokens`

## Current Canonical Implementation References

- `backend/app/services/model_accounting.py`
- `backend/app/services/model_resolver.py`
- `backend/app/agent/execution/service.py`
- `backend/app/db/postgres/models/agents.py`
- `backend/app/db/postgres/models/registry.py`
- `backend/app/api/routers/stats.py`
