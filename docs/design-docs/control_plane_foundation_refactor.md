# Control Plane Foundation Refactor

Last Updated: 2026-04-14

## Summary

The platform architect control-plane foundation now uses a thinner native adapter and a broader shared service layer.

This pass focused on the internal programmable surface, not on public REST/CLI/MCP exposure.

## What Changed

- Added shared control-plane foundation contracts:
  - `ListQuery`
  - `ListPage`
  - `OperationResult`
- Expanded the shared control-plane error model with stable codes for:
  - validation
  - unauthorized / forbidden / scope denied
  - tenant mismatch
  - not found / conflict
  - feature disabled
  - rate limited
  - upstream / internal failures
- Added service-backed admin layers for architect-visible domains:
  - agents
  - rag pipelines/operators/jobs
  - artifacts
  - orchestration primitives
- Migrated the architect-visible REST adapters for:
  - agents
  - rag pipelines/operators/jobs
  - artifacts
  - orchestration primitives
  so tenant-scoped deterministic route execution now uses the same shared admin services as the native platform tools
- Split native control-plane dispatch into domain modules under `backend/app/services/platform_native/`
- Reduced `platform_native_tools.py` to a thin registration/dispatch wrapper

## Native Adapter Rules

The native control-plane tool adapter now follows these rules:

- canonical input is `action` + `payload`
- runtime metadata stays in `__tool_runtime_context__`
- action aliases are not normalized
- publish actions require explicit publish intent
- result payloads do not leak adapter debug markers
- dispatch is service-backed instead of route-function-backed

## Contract Direction

The internal direction is now:

- list-style actions use canonical `skip` + `limit` + `view`
- list responses expose the shared envelope: `items`, `total`, `has_more`, `skip`, `limit`, `view`
- long-running actions use an `operation` envelope

This is prework for future public API, CLI, and MCP adapters.

## Remaining Gaps

- some tenantless admin/support read paths in the RAG routers still use direct route-local query logic
- tool/credential/knowledge-store admin DTOs are still less explicit than the newer agent/rag/artifact DTOs
- orchestration/job lifecycle parity coverage is still shallow
