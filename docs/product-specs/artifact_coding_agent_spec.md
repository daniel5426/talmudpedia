# Artifact Coding Agent Spec

Last Updated: 2026-03-25

This document is the canonical product/runtime contract for `artifact-coding-agent`.

## Purpose

`artifact-coding-agent` is the canonical artifact-authoring coding agent for the platform.

It exists to:
- edit the current artifact draft, including unsaved form state
- inspect and update source files, metadata, runtime settings, and kind-specific contracts
- run artifact test validation against the canonical artifact runtime

## Supported Surfaces

The same agent/runtime contract is used on:
- the artifact page chat
- platform-architect artifact worker delegation

Both surfaces are bound to one current artifact draft session.

## Scope Contract

The agent is always scope-locked to the current bound artifact draft.

Current rules:
- the agent may edit only the current bound draft
- the agent may not switch to another artifact from chat
- the agent may not create, fork, or persist artifacts
- persistence remains owned by the caller surface:
  - artifact page Save/Publish
  - architect binding persistence flow

If a request implies a different artifact identity or an incompatible language change for an existing persisted artifact, the agent must:
- refuse briefly in natural language
- explain that the request is outside the current artifact scope
- stop without mutating the draft

Default refusal behavior must not:
- ask the caller to open another session
- ask the caller to create another artifact
- dump a scaffold or workflow plan unless explicitly asked what to do next

## Authoring Contract

Current authoring rules:
- artifacts may use `python` or `javascript`
- create-mode draft setup may choose the initial `language`
- persisted artifacts must not mutate `language`
- edits must honor the current draft language, runtime target, and file structure
- `tool_impl` artifacts own executable code and `tool_contract` on the artifact draft itself
- tool identity, tool binding, and tool publish pinning remain outside the coding-agent runtime

When the task is to prepare a new artifact draft inside an already-bound create-mode session, the agent should make the draft persistence-ready before claiming completion.

That means filling required draft fields such as:
- `display_name`
- `kind`
- `language`
- `source_files`
- `entry_module_path`
- `runtime_target`
- `capabilities`
- `config_schema`
- exactly one matching kind-specific contract payload

## Tool Surface

The agent uses dedicated artifact `FUNCTION` tools, not shell/sandbox tools.

Current tool groups:
- context/read
  - form state
  - file listing
  - file reads
  - search
  - credential metadata listing
- mutation
  - file edits
  - metadata/runtime updates
  - kind updates
  - contract updates
- validation
  - run artifact test
  - await last test result
  - inspect last test result

Mutation tools update only the persisted shared working-draft snapshot for the current session scope.
They do not mutate canonical artifact rows or revisions directly.

## Credential Contract

The agent may inspect available credentials only through safe metadata listing.

Current rules:
- use credential metadata to discover real credential ids
- never invent credential ids
- credential references in source must be exact string literals of the form `@{credential-id}`
- mixed or embedded forms such as `Bearer @{id}`, concatenations, template strings, comments, or `artifact_runtime_sdk` imports are out of contract

## Validation Contract

Artifact validation must use the canonical artifact runtime.

Current rules:
- use `artifact_coding_run_test` to start validation
- when waiting for outcome, use `artifact_coding_await_last_test_result`
- use `artifact_coding_get_last_test_result` for one-off inspection, not polling loops
- if a test is already queued or running, wait for it instead of starting another one

## Session And Chat Contract

Artifact coding sessions are locked to one artifact or create-mode draft scope.

Current transcript roles are:
- `user`
- `assistant`
- `orchestrator`

Current timeline behavior:
- streamed assistant text and tool calls share one ordered timeline
- assistant text emitted before and after tool calls must remain visible as separate assistant segments
- session-detail history includes assistant delta events and tool events so the ordered timeline can be reconstructed on reload

## Surface-Specific Note

The coding agent contract itself is the same on both supported surfaces.

Surface-specific orchestration remains outside the agent:
- the artifact page owns user-facing save/publish and current-draft editing
- the platform architect owns binding creation, worker spawn/continuation, and any decision to create a different artifact

## Canonical Related Docs

- `docs/product-specs/artifacts_domain_spec.md`
- `docs/product-specs/tools_domain_spec.md`
- `docs/design-docs/artifact_coding_agent_direct_use_current.md`
- `docs/design-docs/platform_architect_worker_orchestration_current.md`
