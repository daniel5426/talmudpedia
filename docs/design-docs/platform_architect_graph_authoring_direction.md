# Platform Architect Graph Authoring Direction

Last Updated: 2026-04-22

## Purpose

Capture the currently agreed direction for the `platform-architect` agent before node-by-node contract work begins.

The main goal of this agent is end-to-end creation of other agents, with RAG/tool integration when needed.

## Decision Summary

The long-term direction is:

- keep strong discovery/research tools for both agent nodes and RAG operators
- move toward canonical graph authoring as the main creation path
- make that graph authoring model-friendly by shifting boilerplate/defaulting into the backend
- defer toolset-loading optimization work until after the authoring contract is improved

This means the target architecture is not:

- four broad container tools with hidden sub-actions
- skills as the primary way to explain schema shape
- shell/helper-only authoring forever

The target architecture is:

- strong node/operator discovery
- canonical graph create/update contracts
- backend normalization/defaulting
- strict validation with useful repair signals

## Why

The current model-facing shape asks the agent to do too much hidden reasoning:

- choose the right domain container
- know which action exists under it
- know the input schema of that action
- shape `action + payload` correctly

That is a weak abstraction boundary for model use.

At the same time, fully generic graph authoring only works if the backend absorbs mechanical complexity. If the model has to author every low-level field itself, reliability drops again.

## Agreed Authoring Model

### 1. Discovery First

The architect should have strong research/read surfaces for:

- `agents.nodes.catalog`
- `agents.nodes.schema`
- `rag.operators.catalog`
- `rag.operators.schema`

These are the foundation for understanding what can be built.

### 2. Canonical Graph Authoring

The preferred long-term authoring path is full graph authoring, not container-tool indirection and not a large collection of special-case create helpers.

The model should author the meaningful structure:

- chosen nodes/operators
- important config choices
- graph connectivity
- high-level resource intent

The backend should own the mechanical parts:

- default values for omitted non-semantic fields
- normalization of accepted graph payloads
- generation of safe boilerplate when unambiguous
- strict structural validation

### 3. Backend Normalization

For this direction to work, graph creation/update must become easier for the model than it is today.

Expected backend responsibilities:

- fill default optional values
- reduce required boilerplate where safe
- keep canonical output shape stable
- return compiler-style validation errors with exact paths and missing fields

### 4. Validation And Repair

Raw graph authoring is only acceptable if the validation path is strong enough to support repair loops.

The backend should return errors that are:

- path-specific
- contract-specific
- easy for the model to repair without guessing

## What Is Deferred

The following is intentionally deferred for a later phase:

- dynamic toolset selection
- per-run toolset narrowing/expansion
- loading optimizations for large action inventories

Those remain important, but they are not the first pass.

## Immediate Working Assumption

For the next phase, the main effort should be:

1. improve node/operator research surfaces
2. improve graph authoring simplicity
3. add backend defaults/normalization where the model currently has to author boilerplate
4. tighten validation and repair signals
5. upgrade the contracts node by node / operator by operator

## Non-Goals For This Doc

This document does not finalize:

- the exact future public MCP surface
- the exact final tool count for the architect
- the exact toolset-loading architecture

It only captures the agreed authoring direction that will guide the next implementation pass.
