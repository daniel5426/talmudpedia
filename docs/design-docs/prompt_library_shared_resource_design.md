# Prompt Library Shared Resource Design

Last Updated: 2026-03-19

## Purpose

Define a new platform-wide prompt library that is authored once and reused across prompt-capable surfaces such as agent instructions, LLM prompts, classify categories, tool descriptions, and schema descriptions.

This is a shared-resource design doc, not an implementation checklist.

## Architectural Placement

The prompt library belongs in Layer 1 (`Shared Resources`) of `docs/design-docs/platform_architecture_layers.md`.

It should be treated like models and tools:
- shared across multiple authored workflow domains
- managed from a control-plane CRUD surface
- consumed by agents, tools, pipelines, and artifacts
- governed by tenant/global visibility rules

Important distinction:
- the prompt library owns reusable prompt assets
- agents/tools/pipelines/artifacts own where those prompts are used

The new page can live under the existing `Agents Management` submenu for now as:
- `/admin/prompts`
- label: `Prompts Library`

That menu placement is a UX choice only. The domain itself is platform-level, not agents-only.

## Proposed Domain Model

Use a DB-backed registry pattern parallel to `ToolRegistry`.

### Canonical record

`PromptLibrary`
- `id`
- `tenant_id` nullable
- `name`
- `description`
- `content`
- `scope` (`tenant` or `global`)
- `status` (`active`, `archived`)
- `version`
- `ownership` (`manual`, `system`)
- `managed_by`
- `allowed_surfaces` JSON/string-list
- `tags` JSON/string-list
- `created_at`
- `updated_at`

`PromptLibraryVersion`
- immutable snapshot of `content` and metadata on create, update, and rollback

## Scope Model

Recommended first-pass scope model:
- tenant-authored prompts are the default
- optional global/system prompts can be supported with `tenant_id = null`

Reason:
- this matches the rest of the control-plane resource model
- it avoids unsafe cross-tenant sharing by default
- it still allows seeded platform prompts later

## Consumption Contract

Do not replace existing string fields with prompt objects in v1.

Use a string-level prompt reference token that can live inside any current text field, including nested JSON schema descriptions.

Recommended token shape:

```text
[[prompt:UUID]]
```

This should be valid in:
- plain prompt fields
- mixed text like `Use this style: [[prompt:brand-voice]]`
- JSON schema `description` strings
- tool descriptions
- classify category descriptions

Why this shape:
- it avoids collisions with current `{{ variable }}` template syntax
- it works without breaking the existing graph spec
- it works inside JSON payloads where values must stay strings
- it keeps persisted references stable even when prompt names change because identity is `id`-backed

## Resolution Strategy

### Authoring-time

Builder/forms should support inserting a prompt reference from a picker rather than forcing users to type the token manually.

Editor interaction should be `@`-driven:
- typing `@` filters prompts by current `name`
- selecting a prompt inserts an ID-backed mention
- the editor renders that mention as the current prompt name
- persisted source remains `[[prompt:UUID]]`

### Runtime

Prompts are always live.

Runtime resolves `[[prompt:UUID]]` against the latest active accessible prompt content on every execution/materialization pass.

Version history exists for audit and rollback, not for publish gating or runtime pinning.

## Surface Discovery Strategy

Prompt eligibility should not be inferred only from ad-hoc frontend checks.

Use backend-driven surface metadata where possible.

### Agent builder

Extend backend operator UI metadata (`AgentOperatorSpec.ui.configFields`) with prompt metadata such as:
- `prompt_capable: true`
- `prompt_surface: "agent.instructions"` or similar

This keeps the source of truth near the operator contract already returned by `/agents/operators`.

### JSON schema surfaces

For raw JSON schema editors, use JSON-pointer-aware detection for string properties named:
- `description`
- `title` later if needed
- `examples` later if needed

V1 should focus on `description`.

## Current Prompt-Capable Surfaces

### Phase 1 targets

These are the highest-value current surfaces confirmed in code:

- Agent builder
  - `agent.instructions`
  - `llm.system_prompt`
  - `classify.instructions`
  - `classify.categories[].description`
  - `rag.query`
  - `vector_search.query`
  - `user_approval.message`
  - `human_input.prompt`
  - `end.output_message`
- Tools registry
  - tool `description`
  - `input_schema` nested `description` strings
  - `output_schema` nested `description` strings
- Agent export to tool
  - export-tool `description`
  - export-tool `input_schema` nested `description` strings
- Pipeline tool-binding settings
  - tool `description`
  - tool `input_schema` nested `description` strings
- Artifact tool contracts
  - `tool_contract.input_schema` nested `description` strings
  - `tool_contract.output_schema` nested `description` strings

### Phase 2 likely targets

- any artifact-authored agent-node config fields marked prompt-capable
- RAG/operator config fields that are truly model-facing instructions
- future prompt-bearing app-builder authoring surfaces

### Explicit non-goals for v1

- end-user chat composer input
- generic entity descriptions that are never consumed by runtime/model behavior
- CEL expression fields

## Frontend Integration Shape

Use one shared prompt-aware input layer instead of page-local implementations.

Recommended pieces:
- `promptsService`
- `PromptPicker`
- `PromptAwareTextarea` / `PromptInsertButton`
- prompt-token rendering helpers for JSON editors

First integrations should hook into the existing shared seams:
- agent builder `SmartInput`
- agent builder `ListEditor`
- tools page textareas
- pipeline tool-settings textareas
- artifact contract JSON editor

## Backend Integration Shape

Recommended new control-plane pieces:
- prompt registry DB model(s)
- `/prompts` API router
- serializer/resolver service for prompt tokens
- publish-time prompt binding snapshot helper

Recommended resolver behavior:
- expand prompt tokens recursively
- detect cycles
- enforce visibility/tenant access
- return both resolved text and binding metadata

Binding metadata should include at least:
- `prompt_id`
- `prompt_version`
- `prompt_name`
- `surface`

## Why Token References Over Structured Field Objects

Token references are the cleanest first cut because they:
- fit existing string contracts
- avoid graph-spec churn
- work inside nested JSON schema descriptions
- allow gradual rollout by surface

Structured prompt-binding objects can still be added later for richer UX, but they are not required to get strong reuse and correct architecture now. The editor can still render rich `@name` mentions while the persisted source stays ID-token based.

## Recommended Rollout

1. Add the prompt-library registry and `/admin/prompts`.
2. Add `@` mention insertion + prompt picker to shared text inputs.
3. Add always-live prompt resolution for agents/tools/pipelines/artifacts at backend materialization/execution seams.
4. Extend JSON schema editors to help insert prompt refs into `description` strings.
5. Add usage indexing later so a prompt page can show “used by”.

## Open Decisions

- whether `allowed_surfaces` should stay exact-match only or support broader surface groups later
- whether prompt usage should remain live-scanned or move to indexed materialization later
