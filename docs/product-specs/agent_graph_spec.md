# Agent Graph Spec

Last Updated: 2026-03-10

This document is the canonical graph-definition contract for the agent builder and backend compiler.

## Purpose

The agent graph spec is the persisted graph format shared by:
- agent builder frontend
- backend graph validation and compilation
- agent save/update flows

## Top-Level Contract

Persisted graph shape:

```json
{
  "spec_version": "1.0",
  "nodes": [],
  "edges": []
}
```

`spec_version` may currently be omitted in legacy payloads, but persisted graphs should carry it explicitly.

## Current Supported Versions

- `1.0`
- `2.0`

Important current rule verified in code:
- if the graph contains GraphSpec v2 orchestration node types, the effective version must be `2.0`
- GraphSpec v2 orchestration is also feature-gated by tenant/surface checks in the backend compiler

## Node Contract

Required fields:
- `id`
- `type`
- `position`
- `config`

Optional fields:
- `label`
- `data`
- `input_mappings`

Current normalization behavior:
- `inputMappings` is normalized to `input_mappings`
- persisted functional config must live in `config`
- builder-only metadata can live in `data`, but `data.config` is not the source of truth

## Edge Contract

Required fields:
- `id`
- `source`
- `target`

Optional fields:
- `type`
- `source_handle`
- `target_handle`
- `label`
- `condition`

Current normalization behavior:
- `sourceHandle` is normalized to `source_handle`
- `targetHandle` is normalized to `target_handle`

## Routing Handle Rules

Current routed/conditional handle patterns include:
- `if_else`: configured conditions plus `else`
- `classify`: configured categories
- `while`: `loop`, `exit`
- `user_approval`: routed handles validated by the compiler

## Current Builder Behavior

The frontend builder normalizes saved graphs by:
- stripping builder-only config duplication from `data`
- moving saved functional configuration into `config`
- serializing `input_mappings`
- serializing normalized edge handles
- resolving the effective `spec_version` based on whether orchestration-v2 nodes are present

## Canonical Implementation References

- `backend/app/agent/graph/schema.py`
- `backend/app/agent/graph/compiler.py`
- `backend/app/services/agent_service.py`
- `frontend-reshet/src/components/agent-builder/graphspec.ts`
