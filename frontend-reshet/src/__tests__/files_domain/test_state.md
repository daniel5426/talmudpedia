Last Updated: 2026-04-16

# Files Domain

## Scope
Files admin client, detail workspace behavior, and unified preview routing for supported file types.

## Test Files
- `file_space_docx_preview.test.tsx`
- `file_space_pdf_preview.test.tsx`
- `file_space_workspace_editor.test.tsx`
- `file_spaces_service.test.ts`
- `file_space_detail_page.test.tsx`
- `file_space_image_preview.test.tsx`
- `file_space_preview_pane.test.tsx`
- `file_space_preview_utils.test.ts`
- `files_page.test.tsx`

## Key Scenarios Covered
- Service routes map to the new `/admin/files` API
- Service binary blob fetches map to the authenticated download endpoint
- Files page loads and renders file spaces from the service
- Files page shows compact file-space stats for file count and total size
- Detail page text editing still participates in unsaved-state and save-all flow
- Preview kind routing distinguishes editable text, image, pdf, docx, and unsupported binaries
- PDF preview renders a bottom page navigator and jump control
- DOCX preview renders a bottom zoom/page dock and supports zoomed drag mode
- File tree opens a shared action card on right click and double click
- Single click does not open the file-tree action card; it only opens on the stricter double-click trigger
- Image preview supports in-pane zoom/reset controls
- Unified preview pane renders image/pdf/docx previews and keeps unsupported files download-only
- Unified preview pane ignores late preview results after unmount/file switch
- DOCX preview renders in-pane with lighter workspace chrome and zoom controls
- PDF and DOCX paged previews use the full editor-pane width instead of the previous capped layout

## Last Run
- Command: `pnpm --dir frontend-reshet test -- --runInBand src/__tests__/files_domain/files_page.test.tsx`
- Date: 2026-04-16 21:25:11 EEST
- Result: Pass (1 suite, 1 test)
- Command: `pnpm --dir frontend-reshet test -- --runInBand src/__tests__/files_domain/file_space_workspace_editor.test.tsx src/__tests__/artifacts_admin/artifact_workspace_editor.test.tsx`
- Date: 2026-04-17 15:20:33 EEST
- Result: Pass (2 suites, 6 tests)

## Known Gaps
- No browser-level visual verification yet for real PDF/DOCX rendering fidelity
- Upload and move flows are still only lightly covered on the frontend side
