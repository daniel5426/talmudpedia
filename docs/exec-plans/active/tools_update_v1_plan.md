# Execution Plan: Tools Update V1

Last Updated: 2026-03-18

## Status: In Progress

This plan tracks the first slice of the tools rework.

## Slice 1: Ownership Clarification

The current tools system has an ownership ambiguity.

At the documentation level, the tools domain is described as a DB-backed registry centered on `/tools`, including artifact-backed tools. At the implementation level, that is only partially true.

There are currently two different ownership models mixed together:

1. Manual tools
- These are truly owned by the tools domain.
- They are created, updated, versioned, and published through `/tools`.

2. Domain-owned bound tools
- `artifact` tools are owned by `tool_impl` artifacts.
- `rag_pipeline` tools are owned by visual/executable pipelines.
- Their lifecycle is not actually managed from `/tools`.
- Instead, their tool rows are created and synchronized by the binding layer.

In practice, `ToolRegistry` is serving two roles at once:
- the runtime-facing callable catalog used by agents
- the authoring source of truth for only some tool types

That mismatch creates confusion in docs, backend behavior, and frontend UX:
- the spec implies `/tools` is the authoring surface for all tools
- the backend rejects normal `/tools` authoring flows for artifact and pipeline tools
- the frontend presents one registry, but some rows are read-only because they belong to another domain

## Proposed Direction For This Slice

We should make ownership explicit instead of implicit.

Target model:

1. Manual tools
- Owned by the tools domain
- Managed in `/tools`

2. Artifact-bound tools
- Owned by artifact authoring
- Mirrored into `ToolRegistry` for runtime selection

3. Pipeline-bound tools
- Owned by pipeline authoring
- Mirrored into `ToolRegistry` for runtime selection

4. System tools
- Owned by backend seeding/runtime code
- Exposed through the same runtime catalog

Under this model, `ToolRegistry` remains the unified agent-facing catalog, but not every row is authored there.

## Why This Slice Comes First

This ownership clarification should come before broader tools cleanup because it determines:
- which API surface is authoritative for each tool type
- which UI surfaces are editable versus read-only
- where publish/version lifecycle belongs
- how docs should describe the tools domain

Without this cut, later cleanup will keep mixing registry concerns with owning-domain concerns.

## Immediate Follow-Up For Later Slices

- add explicit ownership metadata to tool DTOs and persistence
- align the docs with the actual ownership model
- make the tools UI show managed/read-only rows clearly
- keep `/tools` CRUD limited to manual tools
- keep artifact/pipeline publish flows in their owning domains
