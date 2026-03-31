# RAG And Agent Node Architecture Decision

Last Updated: 2026-03-31

## Decision

Do not introduce:
- a unified node registry
- a shared node-definition library
- a projection layer between Agent and RAG node specs

Keep Agent and RAG node registries, node contracts, and executors fully separate.

Accept the small duplication for the few node names that exist in both products, such as:
- `llm`
- `classifier`
- `transform`

## Why

The current overlap is too small to justify a new abstraction layer.

Today the real cost of duplication is low:
- a small number of registration definitions
- occasional duplicated config-field updates

The cost of a shared abstraction would be higher:
- extra architecture to maintain
- composition/wrapper code
- higher regression risk in both products
- extra tests needed only to defend the abstraction

That is a bad trade at the current overlap level.

## Product Boundary Rule

Agent and RAG remain different products with different execution models.

Agent nodes are orchestration/stateful nodes.

RAG nodes are pipeline/dataflow nodes.

Even when two nodes share a similar product name, they are not required to share:
- config shape
- contract model
- UI shape
- runtime behavior
- executor implementation

Natural product drift is acceptable and expected.

## Explicit Non-Goals

This decision means:
- no central registry as a source of truth for Agent and RAG together
- no shared node-definition package used by both products
- no projection layer from a canonical spec into product-specific specs
- no attempt to force Agent and RAG nodes to stay structurally aligned

## When To Revisit

Revisit this decision only if there is concrete evidence that duplication has become expensive. Examples:
- many more nodes are shared across Agent and RAG
- the same bug or config change must repeatedly be fixed in both systems
- product requirements begin to demand stronger cross-surface consistency

Until that happens, the preferred architecture is explicit separation over premature unification.

## Current Implication For RAG Refactor

The RAG node-catalog cleanup should proceed independently.

The target is a better RAG node surface, not shared node architecture with Agent.

Canonical related docs:
- `docs/product-specs/rag_pipeline_spec.md`
- `docs/exec-plans/active/rag_node_catalog_refactor_plan.md`
