# Backend Architecture Overview

Last Updated: 2026-03-10

This file is now a legacy entry point.

The previous content in this file described an older and much simpler backend shape than the one currently implemented. The current canonical backend architecture overview now lives in:

- `docs/design-docs/backend_architecture_current.md`
- `docs/design-docs/agent_execution_current.md`
- `code_architect/architecture_tree.md`

## Why This Changed

The backend is no longer accurately described as a small FastAPI app centered on a classic chat flow plus a narrow RAG workflow. The live codebase now includes:
- a broad domain-based API surface
- graph-based agent and RAG runtimes
- artifact runtime and worker execution
- published app runtime and builder infrastructure
- workload security, quota, and trace systems

## Migration Note

Do not add new long-lived architecture detail here. Use `docs/design-docs/` for canonical architecture documentation.
