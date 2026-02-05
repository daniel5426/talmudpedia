# GraphSpec v1 (Agent Builder)

## Overview
GraphSpec v1 is the canonical, runtime-agnostic graph format used by:
- Agent Builder (frontend)
- Agent Compiler (backend)
- SDK deploy/validate flows

It is versioned and normalized across systems to ensure stable execution and routing.

## Top-level Structure
```
{
  "spec_version": "1.0",
  "nodes": [...],
  "edges": [...]
}
```

## Node Schema (v1)
Required:
- `id`: string
- `type`: string
- `position`: `{ x: number, y: number }`
- `config`: object

Optional:
- `data`: object (ReactFlow data)
- `label`: string
- `input_mappings`: `{ [field: string]: string }`

Notes:
- `input_mappings` is used for artifact nodes to map inputs to state/upstream output.

## Edge Schema (v1)
Required:
- `id`: string
- `source`: string
- `target`: string

Optional:
- `source_handle`: string (branch handle name)
- `target_handle`: string
- `label`: string
- `condition`: string

Notes:
- For conditional routing, `source_handle` must match the handle name defined by the node type.

## Conditional Handle Names
- `if_else`: condition names + `else`
- `classify`: category names
- `while`: `loop`, `exit`
- `user_approval`: `approve`, `reject`
- `conditional`: `true`, `false` (legacy)

## Legacy Normalization
Backend accepts and normalizes:
- `sourceHandle` → `source_handle`
- `targetHandle` → `target_handle`
- `inputMappings` → `input_mappings`

## Versioning Rules
- `spec_version` must be `"1.0"` or omitted (legacy).
- Unsupported versions are rejected by the compiler.
