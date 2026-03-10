# Tools Domain Spec

Last Updated: 2026-03-10

This document is the canonical product/specification overview for the tools domain.

## Purpose

Tools are callable capabilities that agents can execute. The tools domain provides:
- tool registration and versioning
- execution metadata and guardrails
- multiple implementation types
- tenant/global visibility rules

## Current Tool Classes

Current derived tool classes are:
- `built_in`
- `mcp`
- `artifact`
- `custom`

This classification is derived at the API layer rather than stored directly as a database column.

## Current Implementation Types

Current implementation types include:
- `internal`
- `http`
- `rag_retrieval`
- `agent_call`
- `function`
- `custom`
- `artifact`
- `mcp`

## Current API Surface

The main tools API is mounted at:
- `/tools`

Current behavior includes:
- tenant + global tool listing
- create/update/publish/version flows
- tool-type filtering
- sensitive config redaction on reads
- scope-based route protection

## Current Runtime Rules

Current runtime guardrails:
- inactive tools are blocked
- production mode requires published tools
- debug mode can use draft/published tools
- tool resolution enforces tenant visibility

## Current Notable Tool Behaviors

### Retrieval tools

Current retrieval tools normalize the query contract and validate configured pipeline ownership.

### Agent-call tools

Current agent-call tools execute a child-agent run and return compact runtime output.

### Artifact-backed tools

Current artifact-backed tools resolve a tenant artifact revision and execute through the shared artifact runtime.

### MCP tools

Current MCP tools execute through HTTP JSON-RPC `tools/call`.

## Canonical Implementation References

- `backend/app/api/routers/tools.py`
- `backend/app/services/builtin_tools.py`
- `backend/app/agent/executors/tool.py`
- `backend/app/db/postgres/models/registry.py`
