# Files Domain Spec

Last Updated: 2026-04-20

## Summary
`Files` is the durable workspace domain for internal workflows. A file space is a project-scoped workspace that can hold directories and files, be linked to workflows, and be used during internal agent runs.

`attachments` remain thread-scoped chat/runtime objects and are not part of this domain.

## V1 Scope
- Project-shared file spaces only.
- Workflow-level links only.
- Access mode per link is only `read` or `read_write`.
- Internal workflow/runtime surfaces only.
- Text files support read/write/patch.
- Deterministic file representations can be read for supported file types.
- Binary files support upload/download/replace.
- Revisions are per-file immutable revisions only.

## Core Objects
- `file_spaces`
  - Durable project workspace container.
- `file_space_entries`
  - Current live tree entries by path.
- `file_entry_revisions`
  - Immutable content revisions for files.
- `agent_file_space_links`
  - Workflow-to-file-space links with access mode.

## Behavior
- A file space can contain nested directories and files.
- Every file write creates a new immutable revision.
- The current tree points to the latest revision for each file.
- Directory operations mutate the live tree only.
- Deleted entries are removed from the live tree while prior revisions remain preserved.

## Workflow Runtime Contract
- Workflow links are configured on the workflow/agent.
- Every node/tool/artifact in that workflow run can use the linked spaces.
- Run context injects only file-space metadata:
  - `context.file_spaces = [{ id, name, access_mode }]`
- File contents are never preloaded into prompts or run context.
- Access happens on demand through file tools.
- Runtime file access authorization is reusable backend infrastructure, not a `files.*`-specific special case.
- Generic tools may consume authorized file references using canonical `space_id + path`.

## Tool Surface
- `files.list`
- `files.inspect`
- `files.read`
- `files.read_representation`
- `files.write`
- `files.patch_text`
- `files.mkdir`
- `files.move`
- `files.delete`
- `files.upload_blob`
- `files.download_meta`

Backend enforcement is authoritative for `read` vs `read_write`.

Current deterministic representation examples:
- `raw_text`
- `markdown_rendered`
- `delimited_table`
- `workbook`
- `document_text`
- `binary_meta`

## Toolset UX
- linked file-space access is grouped in the tools catalog as the `file_space_memory` toolset
- the toolset is a builder-selection convenience over the same `files.*` tools
- selecting the toolset expands to the member tool ids before save; runtime behavior remains the normal flat file-tool surface

## Control-Plane Surface
- File-space CRUD/list/detail
- Tree listing
- Text read/write/patch
- Directory create
- Entry move/delete
- Binary upload/download
- File revision history
- Workflow link create/list/delete

## Explicit Non-Goals In V1
- Per-node permissions
- Artifact-level file links
- Path-scoped mounts or aliases
- Whole-space snapshots
- Git-style branching/commits
- Published/embed/public runtime exposure
