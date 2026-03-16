# Classic Chat Template Reference

Last Updated: 2026-03-16

This document describes the current `classic-chat` published-app starter template.

## Purpose

`classic-chat` is the current replacement starter for the deleted legacy published-app template catalog.

It is intended to be:
- a single canonical starter instead of a broad theme catalog
- a Base44-style React app shell built from shadcn/Radix primitives
- a strong default for chat-first apps, internal tools, CRUD surfaces, and fast iteration in Apps Builder

Current source location:
- `backend/app/templates/published_apps/classic-chat/`

Current template-pack contract:
- folder name: `classic-chat`
- template key: `classic-chat`
- entry file: `src/main.tsx`

## Current Base Page

The current starter now includes a chat-first base page implemented as a modular ChatGPT-style shell:
- playground-inspired sticky header
- left sidebar with `new chat` and paginated history
- centered welcome state with prompt composer
- conversation timeline with inline task/tool rows
- assistant action row under responses
- bottom composer with scroll-to-bottom affordance above it

The implementation is intentionally split into template-local feature modules instead of one large app component.

## Current Stack

- Build/runtime:
  - Vite
  - React 19
  - TypeScript
- Styling and UI primitives:
  - Tailwind CSS v4
  - shadcn CLI-generated component set
  - Radix-style primitives via the generated shadcn stack
  - `class-variance-authority`
  - `clsx`
  - `tailwind-merge`
  - `tw-animate-css`
- App/runtime ergonomics:
  - `react-router-dom`
  - `@tanstack/react-query`
  - `next-themes`
- Forms and validation:
  - `react-hook-form`
  - `@hookform/resolvers`
  - `zod`
- Supporting UI packages currently present:
  - `cmdk`
  - `date-fns`
  - `embla-carousel-react`
  - `input-otp`
  - `lucide-react`
  - `react-day-picker`
  - `react-resizable-panels`
  - `recharts`
  - `sonner`
  - `vaul`
- Styling/font assets currently present:
  - `@fontsource-variable/noto-sans`
  - `@remixicon/react`

## Current Dependencies

Current production dependencies from `backend/app/templates/published_apps/classic-chat/package.json`:

```json
{
  "@fontsource-variable/noto-sans": "^5.2.10",
  "@hookform/resolvers": "^5.2.2",
  "@remixicon/react": "^4.9.0",
  "@tailwindcss/vite": "^4.1.17",
  "@tanstack/react-query": "^5.90.21",
  "class-variance-authority": "^0.7.1",
  "clsx": "^2.1.1",
  "cmdk": "^1.1.1",
  "date-fns": "^4.1.0",
  "embla-carousel-react": "^8.6.0",
  "input-otp": "^1.4.2",
  "lucide-react": "^0.577.0",
  "next-themes": "^0.4.6",
  "radix-ui": "^1.4.3",
  "react": "^19.2.0",
  "react-day-picker": "^9.14.0",
  "react-dom": "^19.2.0",
  "react-hook-form": "^7.71.2",
  "react-resizable-panels": "^4.7.3",
  "react-router-dom": "^7.13.1",
  "recharts": "2.15.4",
  "shadcn": "^4.0.8",
  "sonner": "^2.0.7",
  "tailwind-merge": "^3.5.0",
  "tailwindcss": "^4.1.17",
  "tw-animate-css": "^1.4.0",
  "vaul": "^1.1.2",
  "zod": "^4.3.6"
}
```

Current dev dependencies:

```json
{
  "@eslint/js": "^9.39.1",
  "@types/node": "^24.10.1",
  "@types/react": "^19.2.5",
  "@types/react-dom": "^19.2.3",
  "@vitejs/plugin-react": "^5.1.1",
  "eslint": "^9.39.1",
  "eslint-plugin-react-hooks": "^7.0.1",
  "eslint-plugin-react-refresh": "^0.4.24",
  "globals": "^16.5.0",
  "prettier": "^3.8.1",
  "prettier-plugin-tailwindcss": "^0.7.2",
  "typescript": "~5.9.3",
  "typescript-eslint": "^8.46.4",
  "vite": "^7.2.4"
}
```

## Installed shadcn UI Surface

Current generated UI components under `src/components/ui/`:

- `accordion`
- `alert`
- `alert-dialog`
- `aspect-ratio`
- `avatar`
- `badge`
- `breadcrumb`
- `button`
- `calendar`
- `card`
- `carousel`
- `chart`
- `checkbox`
- `collapsible`
- `command`
- `context-menu`
- `dialog`
- `drawer`
- `dropdown-menu`
- `hover-card`
- `input`
- `input-group`
- `input-otp`
- `label`
- `menubar`
- `navigation-menu`
- `pagination`
- `popover`
- `progress`
- `radio-group`
- `resizable`
- `scroll-area`
- `select`
- `separator`
- `sheet`
- `sidebar`
- `skeleton`
- `slider`
- `sonner`
- `switch`
- `table`
- `tabs`
- `textarea`
- `toggle`
- `toggle-group`
- `tooltip`

Additional template component currently present:
- `src/components/theme-provider.tsx`

## Installed AI Elements Surface

Current AI elements available under `src/components/ai-elements/` and directly relevant to the base page:

- `conversation`
- `message`
- `prompt-input`
- `task`
- `chain-of-thought`
- `inline-citation`
- `suggestion`
- `shimmer`
- `attachments`
- `sources`

Other installed AI elements remain available for later template expansion, but the current base page centers on the set above.

## Current Design Direction

- The starter is shadcn-first rather than custom-CSS-first.
- It favors composable primitives over a fully prebuilt app theme.
- The base page follows the platform playground interaction model rather than a generic SaaS dashboard shell.
- Tool calls are intentionally rendered inline with assistant content using `Task`, not grouped into a separate panel at the top of the response.
- It is suitable as the base shell for:
  - chat products
  - internal admin tools
  - dashboards
  - CRUD-heavy workflows
- It should remain a single canonical starter until the platform proves a real need for multiple differentiated templates.

## Current Implemented Structure

The current base page is organized around:
- `ClassicChatApp`
- sidebar shell
- sticky header
- empty-state welcome/composer
- timeline renderer
- inline assistant action row
- typed local state hook with mock thread/message/task data

The current implementation is runtime-ready in shape, but still local-state-driven.

## Current Gaps

- [/] The template still needs to be normalized into the backend template-pack contract.
- Expected follow-up work:
  - add `template.manifest.json`
  - ensure `vite.config.*` sets `base: "./"`
  - remove local-only project noise such as `.git/` and `node_modules/`
  - [x] confirm compatibility with runtime bootstrap overlay files injected by `published_app_templates.py`
- [/] replace remaining local thread/message state assumptions with full runtime SDK history adapters

## Runtime Contract Note

- The template’s runtime SDK integration for host-anywhere clients now targets `/public/external/apps/{slug}/*`.
- Platform-hosted same-origin published runtime still uses injected host-runtime bootstrap and `/_talmudpedia/*` routes.

## Related Docs

- `docs/design-docs/apps_builder_current.md`
- `backend/documentations/Templates.md`
- `docs/product-specs/runtime_sdk_host_anywhere_spec.md`
