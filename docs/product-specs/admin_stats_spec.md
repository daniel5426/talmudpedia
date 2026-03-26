# Admin Stats Spec

Last Updated: 2026-03-26

This document is the canonical product/specification overview for the admin stats surface.

## Purpose

The admin stats surface provides tenant-scoped operational metrics for:
- overview
- RAG
- agents
- resources

## Current Endpoint

Current live backend path:
- `GET /admin/stats/summary`

This corrects older docs that referenced `/api/v1/admin/stats/summary`.

## Current Parameters

- `section`
- `days`
- `start_date`
- `end_date`
- optional `agent_id` when `section=agents`

Current section values:
- `overview`
- `rag`
- `agents`
- `resources`

## Current Access Model

The backend currently uses a tenant context derived from the current user’s membership path inside the stats router.

This means the stats surface is tenant-scoped, but it does not yet use the newer shared principal/scope dependency pattern used by many other control-plane routes.

## Current Metric Families

### Overview

Current overview metrics include:
- users
- chats/messages
- persisted run-accounting totals
- exact vs estimated token coverage
- exact vs estimated spend coverage
- unknown usage/cost coverage
- top users
- top models

### RAG

Current RAG metrics include:
- knowledge store summaries
- pipeline counts
- job duration and failure summaries

### Agents

Current agent metrics include:
- run counts and status trends
- persisted run-accounting totals
- exact vs estimated token coverage
- exact vs estimated spend coverage
- unknown usage/cost coverage
- duration and queue metrics
- top agents and failure summaries

### Resources

Current resource metrics include:
- tools
- models
- provider bindings
- artifacts

## Current Frontend Surface

Current frontend page:
- `frontend-reshet/src/app/admin/stats/page.tsx`

The frontend uses centralized service/types under `frontend-reshet/src/services/`.

The admin dashboard overview should also read from the summary-based overview contract rather than the legacy `/admin/stats` payload.

## Current Accounting Contract

The stats surface now aggregates persisted run-accounting fields on `agent_runs` rather than recomputing spend from a dashboard-only heuristic.

Current accounting response fields exposed on overview and agents include:
- `total_tokens`
- `total_tokens_exact`
- `total_tokens_estimated`
- `runs_with_unknown_usage`
- `estimated_spend_usd`
- `total_spend_exact_usd`
- `total_spend_estimated_usd`
- `runs_with_unknown_cost`

Current accounting rules:
- `total_tokens` rolls up persisted run totals with legacy `usage_tokens` as compatibility fallback
- exact token totals include provider-reported and SDK-reported usage
- estimated token totals include explicitly estimated rows only
- spend is aggregated from persisted `cost_usd`
- unknown usage/cost rows remain visible as coverage counts instead of being silently priced

## Current Agent Drilldown

The `agents` section now supports optional per-agent drilldown:
- `GET /admin/stats/summary?section=agents&agent_id=<agent_uuid>`

When `agent_id` is present:
- run totals are scoped to that agent
- time-series metrics are scoped to that agent
- top-user/run attribution is scoped to that agent
- top-agent lists may collapse to the selected agent

## Canonical Implementation References

- `backend/app/api/routers/stats.py`
- `backend/app/api/schemas/stats.py`
- `backend/app/services/model_accounting.py`
