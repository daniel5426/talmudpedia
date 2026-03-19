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
- `slug`
- `description`
- `content`
- `scope` (`tenant` by default, optional `global/system` later)
- `status` (`draft`, `published`, `archived` or equivalent)
- `version`
- `ownership` (`manual`, optional `system`)
- `managed_by`
- `allowed_surfaces` JSON/string-list
- `tags` JSON/string-list
- `created_at`
- `updated_at`
- `published_at`

`PromptLibraryVersion`
- immutable snapshot of `content` and metadata at publish time

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
[[prompt:customer-support-classifier]]
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

## Resolution Strategy

### Authoring-time

Builder/forms should support inserting a prompt reference from a picker rather than forcing users to type the token manually.

### Draft execution

Draft surfaces may resolve against the latest accessible prompt version for fast iteration.

### Publish/runtime

Published runtime should not dynamically fetch mutable prompt content by slug on every run.

Instead:
1. authored objects keep the reference token
2. publish/compile resolves prompt references to concrete content
3. the published snapshot stores prompt-version bindings
4. runtime executes against the published resolved snapshot

This prevents silent behavior drift when a library prompt changes after an agent/tool/pipeline was published.

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
- `prompt_slug`
- `prompt_version`
- `surface`

## Why Token References Over Structured Field Objects

Token references are the cleanest first cut because they:
- fit existing string contracts
- avoid graph-spec churn
- work inside nested JSON schema descriptions
- allow gradual rollout by surface

Structured prompt-binding objects can still be added later for richer UX, but they are not required to get strong reuse and correct architecture now.

## Recommended Rollout

1. Add the prompt-library registry and `/admin/prompts`.
2. Add token insertion + prompt picker to shared text inputs.
3. Add publish-time resolution and binding snapshots for agents/tools/pipelines.
4. Extend JSON schema editors to help insert prompt refs into `description` strings.
5. Add usage indexing later so a prompt page can show “used by”.

## Open Decisions

- exact status enum names for prompts
- whether published prompt slugs are immutable
- whether `allowed_surfaces` is enforced or advisory in v1
- whether draft execution resolves latest draft or latest published by default
