# React Artifacts Live Preview

Last Updated: 2026-02-06

## Overview
This feature adds a Claude-style “artifact” experience to chat. When an assistant response contains a React code fence (```tsx, ```jsx, or ```react), the UI opens a right-side panel with a live editor and preview. The preview compiles entirely in the browser via `esbuild-wasm` and renders inside a sandboxed iframe.

## What Users See
- **Auto-open panel** when a React code fence is detected in an assistant response.
- **Editor + live preview** side-by-side with the chat.
- **Console output** captured from the preview.
- **Manual actions:** Run, Reset, Close.

## Triggering Rules
- Only the **first** fenced block with language `tsx`, `jsx`, or `react` is used.
- Streaming messages are ignored; only final assistant messages are parsed.

## Compilation & Runtime
- Compilation uses **`esbuild-wasm`** entirely in the browser.
- The compiler only allows the following imports:
  - `react`
  - `react-dom/client`
  - `react/jsx-runtime`
  - `react/jsx-dev-runtime`
- Any other import is rejected with a clear build error.
- React/ReactDOM are pinned to a fixed CDN version to avoid duplicate React instances.

## Tailwind Support
The preview iframe injects Tailwind via CDN (`https://cdn.tailwindcss.com`) so Tailwind classes render correctly in artifacts. This is limited to the preview iframe only.

## Security Model
- The preview runs inside a sandboxed iframe (`sandbox="allow-scripts"`).
- CSP for the iframe is restrictive and only allows inline styles/scripts plus the Tailwind CDN script.
- No network access is granted from the preview except the Tailwind CDN.

## Persistence
Artifacts are stored locally in `localStorage` per tenant + chat using a namespaced key:
```
react-artifact:v1:${tenant}:${chat}
```
There is no backend persistence at this stage.

## Key Files
- `frontend-reshet/src/components/ai-elements/ReactArtifactPane.tsx`
- `frontend-reshet/src/components/layout/ChatPane.tsx`
- `frontend-reshet/src/app/admin/agents/playground/page.tsx`
- `frontend-reshet/src/lib/react-artifacts/parseReactArtifact.ts`
- `frontend-reshet/src/lib/react-artifacts/compiler.ts`
- `frontend-reshet/src/lib/react-artifacts/useReactArtifactPanel.ts`

## Smoke Test
1. Go to `/chat` or `/admin/agents/playground`.
2. Ask the assistant for a React component in a ```tsx fence.
3. Confirm the right panel opens, the preview renders, and console output appears.
4. Add a disallowed import (e.g., `lodash`) to confirm the build error is shown.

## Known Limitations
- No external libraries beyond React/ReactDOM.
- Tailwind depends on CDN network access in the preview.
- No multi-file support or relative imports.
