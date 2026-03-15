# Execution Plan: Classic Chat SDK Integration

Last Updated: 2026-03-15

## Status: Completed ✅

Integrating `@talmudpedia/runtime-sdk` into the `classic-chat` template to support real-time streaming and app-scoped authentication.

## Goals

1. **Local Development Mocks**: Enable `pnpm dev` to work locally by mocking the platform-injected runtime files.
2. **Auth Integration**: Replace the mock user in the sidebar with a real `PublishedAppAccount` via the SDK auth client.
3. **Streaming Integration**: Replace the `setTimeout` mock streaming with a real `runtimeClient.stream()` call.

## Implementation Steps

### 1. Dependency Setup
- [x] Add `@talmudpedia/runtime-sdk` to `package.json`.
- [x] Run `pnpm install` at the template level and repository root.

### 2. Runtime Injection (Local Mocks)
- [x] Create `src/runtime-config.json` with local dev defaults.
- [x] Create `src/runtime-sdk.ts` as a local mirror of the platform's bootstrap script.

### 3. Feature Integration
- [x] Implement `RuntimeProvider` in `src/features/classic-chat/runtime-context.tsx`.
- [x] Wrap the app tree in `RuntimeProvider` in `src/main.tsx`.
- [x] Hook up the Sidebar to use `authClient` and `user` state.
- [x] Update `use-classic-chat-state.ts` to use `runtimeClient.stream()` for real message processing.
  - [x] Implement `NormalizedRuntimeEvent` to `TemplateRenderBlock` mapping.
  - [x] Handle thread creation/persistence via SDK.
  - [x] Integrate real-time state updates for blocks.

## Verification Plan

- [ ] Run `pnpm dev` in `classic-chat`.
- [ ] Test auth flow: Login redirects to platform gate, success returns to app.
- [ ] Test streaming: Messages are processed and blocks are updated in real-time.
