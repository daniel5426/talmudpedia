# Templates

Last Updated: 2026-02-12

## Current State Summary
- Template packs root: `backend/app/templates/published_apps/`
- Active templates: `chat-classic`, `chat-grid`, `chat-editorial`, `chat-neon`, `chat-soft`
- Loader behavior: templates are loaded from disk on each call (no in-memory `lru_cache`), so file edits are picked up without restarting just for template file reads.
- Strategy currently implemented: clean implementation only (no legacy fallback paths kept).

## Template Catalog (Manifest State)

| Key | Name | Description | Tags | Entry |
|---|---|---|---|---|
| `chat-classic` | Classic Dialogue | Balanced chat-first layout with subtle panels. | `chat`, `neutral` | `src/main.tsx` |
| `chat-grid` | Layout Shell Premium | LayoutShell-style workspace with sidebar, resizable source viewer, and mobile overlays. | `chat`, `premium`, `workspace` | `src/main.tsx` |
| `chat-editorial` | Editorial Stack | High-contrast editorial style for premium assistants. | `chat`, `editorial` | `src/main.tsx` |
| `chat-neon` | Neon Console | Dark neon style with bold contrast and sharp edges. | `chat`, `dark` | `src/main.tsx` |
| `chat-soft` | Soft Product | Rounded, calm interface for customer-facing support flows. | `chat`, `friendly` | `src/main.tsx` |

## What Is Special Right Now
- `chat-classic` is the advanced template and currently includes the largest component set, including:
  - vendored shadcn/radix-style UI layer under `src/components/ui/*`
  - AI interaction elements under `src/components/ai-elements/*`
  - app-level composition via `Sidebar`, `BotInputArea`, `Message`, `ChainOfThought`
  - support utilities/hooks/stubs under `src/lib/*`, `src/hooks/*`, `src/services/*`
- Other templates (`chat-grid`, `chat-editorial`, `chat-neon`, `chat-soft`) remain lighter and mostly depend on base React/Vite stack.

## Dependency Policy (Builder Validation)
- Enforced by: `backend/app/services/apps_builder_dependency_policy.py`
- Only allowlisted packages are valid; declared versions must exactly match pinned versions.
- Import rules currently enforced:
  - local relative imports (`./`, `../`) allowed
  - alias imports (`@/...`) allowed
  - `node:` imports allowed
  - network imports (`http(s)://`) blocked
  - undeclared/unsupported packages blocked
- `chat-classic` now validates under policy with expanded allowlist (Radix packages, `ai`, `cmdk`, `clsx`, `class-variance-authority`, `lucide-react`, `nanoid`, `streamdown`, `tailwind-merge`, plus Tailwind/PostCSS toolchain).

## Runtime/Preview State Relevant To Templates
- Preview runtime now returns preview URL based on built manifest entry HTML (`.../assets/{entry_html}`) and appends a preview token.
- Preview auth bridge supports:
  - bearer token
  - `preview_token` query param
  - `published_app_preview_token` cookie
- Result: built template previews can load `index.html` + JS assets when opened from builder preview flow.

## Operational Notes
- For local testing through the builder, backend + worker must be running and using latest code.
- If you change backend validation/build code and still see old “Unsupported package ...” errors, restart the backend process and Celery worker so active processes load the latest policy code.

## Local Template Debug Loop (No Worker Roundtrip)
- Run a template directly with Vite + HMR:
  - `bash backend/scripts/dev-services/template_local_dev.sh chat-classic`
- Switch templates quickly:
  - `bash backend/scripts/dev-services/template_local_dev.sh chat-grid --port 4174`
- Force dependency reinstall when needed:
  - `bash backend/scripts/dev-services/template_local_dev.sh chat-classic --install`
- Build-check before pushing template changes:
  - `bash backend/scripts/dev-services/template_build_all.sh`

## Tailwind Wiring (`chat-classic`)
- `chat-classic` now has explicit Tailwind wiring:
  - `tailwind.config.ts`
  - `postcss.config.cjs`
  - `@tailwind base/components/utilities` directives in `src/styles.css`
- `tailwindcss-animate` is included for shadcn-style animation utilities (`animate-in`, `fade-in-*`, `slide-in-*`, `zoom-*`).
- Class syntax that was Tailwind v4-style (`w-(--var)`, `origin-(--var)`, `max-h-(--var)`) was normalized to Tailwind v3-compatible arbitrary values (`w-[var(--...)]`, `origin-[var(--...)]`, `max-h-[var(--...)]`).
- Result: Tailwind utility classes used by `chat-classic` UI components are now emitted in local/worker builds instead of being silently skipped.

## Source of Truth Files
- Template loader: `backend/app/services/published_app_templates.py`
- Dependency policy: `backend/app/services/apps_builder_dependency_policy.py`
- Template packs: `backend/app/templates/published_apps/*`
- Plan tracking: `backend/documentations/Plans/Base44_Vite_Static_Apps_ImplementationPlan.md`
