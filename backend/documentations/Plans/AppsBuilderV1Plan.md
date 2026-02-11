# Apps Builder V1 (Phased, Contract-First)
Last Updated: 2026-02-11

## Summary
Deliver in 3 milestones (not one pass), with contracts locked first for concurrency, compile policy, preview auth, stream transport, and publish semantics.

## Milestone 0: Contract Lock (no UI build yet)
1. Finalize API contracts and schemas:
- `POST /admin/apps` accepts `template_key`, `slug` optional.
- `POST /admin/apps/{id}/builder/revisions` uses optimistic concurrency.
- `POST /admin/apps/{id}/builder/chat/stream` emits patch ops contract.
- `POST /admin/apps/{id}/publish` clones current draft into published snapshot revision.
- `GET /public/apps/{slug}/ui` returns published UI snapshot only.

2. Lock concurrency response:
- On stale `base_revision_id`, return `409` with payload:
  - `code: "REVISION_CONFLICT"`
  - `latest_revision_id`
  - `latest_updated_at`
  - `message`

3. Lock compile/import policy:
- Virtual multi-file project only.
- Allow relative imports inside virtual tree.
- Allow package imports only: `react`, `react-dom/client`, `react/jsx-runtime`, `react/jsx-dev-runtime`.
- Block network and absolute imports.
- Limits: max files, max per-file size, max total project size, max compile time.

4. Lock preview token model:
- New short-lived preview token (5 min TTL), claims:
  - `sub` (admin user id)
  - `tenant_id`
  - `published_app_id`
  - `revision_id`
  - `scopes: ["apps.preview"]`
  - `jti`, `exp`
- New dependency validator for preview endpoints.

5. Lock runtime config visibility semantics:
- Keep current `GET /public/apps/{slug}/config` behavior (status visible by slug).
- New `/ui` endpoint is published-only and never leaks draft files/bundle.

6. Migration sequencing rule:
- New alembic revision must chain from current latest head (`b2f4c6d8e9a1...`), not older Apps migration.

## Milestone 1: Data + Create Flow + Builder State
1. Backend:
- Add `published_app_revisions` table.
- Add lightweight pointers on `published_apps`:
  - `current_draft_revision_id`
  - `current_published_revision_id`
- Seed template manifests (5 templates).
- On app create:
  - auto-generate slug from name
  - create initial draft revision from selected template.

2. Frontend:
- Expand create modal in `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/app/admin/apps/page.tsx`.
- Remove visible slug field.
- Add 5 template cards.
- Redirect create success to `/admin/apps/[id]`.

3. API/types:
- Centralized in `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/services/`.
- Add types: template, revision, builder state, conflict response.

4. Tests:
- Backend create-with-template + slug autogen + initial draft revision.
- Frontend create modal template selection + payload + redirect.

## Milestone 2: Builder Workspace (Preview/Code, no AI patching yet)
1. Route and layout:
- `/admin/apps/[id]` becomes builder default route.
- Top tabs: `Preview` (default), `Code`.
- Right panel reserved for edit chat UI shell.
- App sidebar auto-collapses on entry.

2. Preview tab:
- Live preview from draft revision using existing sandboxed iframe compile flow, upgraded to multi-file.

3. Code tab:
- Base44-style file tree + Monaco editor.
- Full editability of client-visible virtual files only.
- Save creates new draft revision.

4. Feature-scoped cleanup:
- New module: `/Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/features/apps-builder/`
  - `templates/`, `workspace/`, `preview/`, `editor/`, `state/`, `runtime-sdk/`

5. Tests:
- Tab switching, file tree rendering, file edit/save revision creation, preview refresh.

## Milestone 3: AI Patch Editing + Template Switch + Publish Snapshot
1. Builder chat endpoint:
- Dedicated app-builder SSE endpoint.
- Returns structured patch ops at completion.

2. Patch apply pipeline:
- Validate ops against allowlist and file constraints.
- Apply in-memory.
- Compile.
- Save new draft revision if valid.
- Surface compile errors otherwise.

3. Template switching:
- Settings action: switch template with destructive confirmation.
- Creates new draft revision by full overwrite from template baseline.

4. Publish:
- Clone current draft to published revision snapshot.
- Public runtime serves only published snapshot from `/public/apps/{slug}/ui`.

5. Stream transport:
- Builder streaming calls bypass buffering path (same principle as agent streaming direct backend usage).

6. Tests:
- Patch ops success/failure.
- Template reset overwrite behavior.
- Publish snapshot immutability.
- Public UI serves published snapshot only.

## Public Interfaces / Types Added
1. `PublishedAppTemplate`:
- `key`, `name`, `description`, `thumbnail`, `style_tokens`, `entry_file`.

2. `PublishedAppRevision`:
- `id`, `published_app_id`, `kind`, `template_key`, `entry_file`, `files`, `compiled_bundle`, `created_at`, `source_revision_id`.

3. `BuilderPatchOp` union:
- `upsert_file`, `delete_file`, `rename_file`, `set_entry_file`.

4. `RevisionConflictResponse`:
- `code`, `latest_revision_id`, `latest_updated_at`, `message`.

## Explicit Assumptions / Defaults
1. Builder is primary app screen.
2. Slug is hidden at create and auto-generated.
3. Template switching is allowed and overwrites current draft after confirmation.
4. Published runtime serves published snapshot only.
5. Refactor is feature-scoped, not whole-frontend reorg.
6. Dedicated builder chat backend is required in v1.
7. Existing docs currently contradict this direction (`Apps.md` says no template customization); update docs during implementation.

## Implementation Status
### Last Updated: 2026-02-11
### Completed
- [x] Milestone 1 backend schema/model work landed: `published_app_revisions`, app draft/published revision pointers, and migration chained from `b2f4c6d8e9a1`.
- [x] Milestone 1 create flow landed: `POST /admin/apps` supports optional `slug`, accepts `template_key`, and auto-generates slug server-side.
- [x] Milestone 1 builder seed/template contracts landed: `GET /admin/apps/templates` and template manifest service with 5 templates.
- [x] Milestone 1 builder state endpoint landed: `GET /admin/apps/{app_id}/builder/state`.
- [x] Milestone 1 frontend create modal landed: slug removed, larger modal, template cards, template selection in payload, redirect to `/admin/apps/{id}`.
- [x] Milestone 1 service/type centralization landed in `src/services/published-apps.ts` and `src/services/index.ts`.
- [x] Milestone 2 route behavior landed: `/admin/apps/[id]` now opens builder workspace by default.
- [x] Milestone 2 workspace UI landed: `Preview | Code` tabs, center workspace, right builder chat panel shell, sidebar auto-close.
- [x] Milestone 2 preview tab landed on multi-file sandbox compile path.
- [x] Milestone 2 code workspace landed with virtual file explorer + code editor and draft save to revisions endpoint.
- [x] Milestone 2 feature-scoped module landed at `frontend-reshet/src/features/apps-builder/`.
- [x] Milestone 3 builder SSE endpoint landed: `POST /admin/apps/{app_id}/builder/chat/stream`.
- [x] Milestone 3 revisions write endpoint landed: `POST /admin/apps/{app_id}/builder/revisions` with optimistic concurrency and `REVISION_CONFLICT` 409 contract.
- [x] Milestone 3 template reset endpoint landed: `POST /admin/apps/{app_id}/builder/template-reset`.
- [x] Milestone 3 publish semantics landed: publish clones latest draft into new published snapshot revision and updates pointers.
- [x] Milestone 3 public UI runtime landed: `GET /public/apps/{slug}/ui` serves published snapshots only.
- [x] Milestone 3 preview auth landed: short-lived preview token + validator dependency for preview UI fetch.
- [x] Public interfaces/types landed: `PublishedAppTemplate`, `PublishedAppRevision`, `BuilderPatchOp`, `RevisionConflictResponse`.
- [x] Backend/Frontend tests expanded for builder flow and updated for new contracts.
### In Progress
- None.
### Deferred
- None.
### File-Level Changes
- /Users/danielbenassaya/Code/personal/talmudpedia/backend/alembic/versions/c4d5e6f7a8b9_add_published_app_revisions_builder_v1.py
- /Users/danielbenassaya/Code/personal/talmudpedia/backend/app/api/dependencies.py
- /Users/danielbenassaya/Code/personal/talmudpedia/backend/app/api/routers/published_apps_admin.py
- /Users/danielbenassaya/Code/personal/talmudpedia/backend/app/api/routers/published_apps_public.py
- /Users/danielbenassaya/Code/personal/talmudpedia/backend/app/core/security.py
- /Users/danielbenassaya/Code/personal/talmudpedia/backend/app/db/postgres/models/__init__.py
- /Users/danielbenassaya/Code/personal/talmudpedia/backend/app/db/postgres/models/published_apps.py
- /Users/danielbenassaya/Code/personal/talmudpedia/backend/app/services/published_app_templates.py
- /Users/danielbenassaya/Code/personal/talmudpedia/backend/tests/conftest.py
- /Users/danielbenassaya/Code/personal/talmudpedia/backend/tests/published_apps/test_admin_apps_crud.py
- /Users/danielbenassaya/Code/personal/talmudpedia/backend/tests/published_apps/test_admin_apps_publish_rules.py
- /Users/danielbenassaya/Code/personal/talmudpedia/backend/tests/published_apps/test_builder_revisions.py
- /Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/app/admin/apps/page.tsx
- /Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/app/admin/apps/[id]/page.tsx
- /Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/app/published/[appSlug]/page.tsx
- /Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/features/apps-builder/templates/index.ts
- /Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/features/apps-builder/workspace/AppsBuilderWorkspace.tsx
- /Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/features/apps-builder/preview/PreviewCanvas.tsx
- /Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/features/apps-builder/editor/VirtualFileExplorer.tsx
- /Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/features/apps-builder/state/useBuilderDraft.ts
- /Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/features/apps-builder/runtime-sdk/index.ts
- /Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/lib/react-artifacts/compiler.ts
- /Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/services/index.ts
- /Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/services/published-apps.ts
- /Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/services/published-runtime.ts
- /Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/__tests__/published_apps/apps_admin_page.test.tsx
- /Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/__tests__/published_apps/apps_builder_workspace.test.tsx
- /Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/__tests__/published_apps/published_chat_template.test.tsx
- /Users/danielbenassaya/Code/personal/talmudpedia/frontend-reshet/src/__tests__/published_apps/published_runtime_gate.test.tsx
### Validation
- `pytest backend/tests/published_apps -q` -> PASS (12 passed).
- `cd frontend-reshet && npm test -- --runInBand src/__tests__/published_apps` -> PASS (5 suites, 7 tests).
### Follow-ups
- Add stronger backend-side builder patch validation/compile guardrails (file-count/size/time ceilings) before wider rollout.
- Add targeted API tests for preview-token expiry and invalid-claims rejection paths.
- Add end-to-end builder publish verification test across create -> edit -> publish -> public `/ui` runtime render.
