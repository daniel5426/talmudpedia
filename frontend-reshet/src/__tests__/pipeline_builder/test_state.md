# Pipeline Builder Test State

Last Updated: 2026-04-01

## Scope
- Frontend pipeline-builder save/run feedback around explicit compile materialization.

## Test files present
- `pipeline_run_stale_executable.test.tsx`

## Key scenarios covered
- The editor blocks run when the visual draft is newer than the latest executable.
- The user sees a compile-required message instead of a generic failure.

## Last run command + date/time + result
- Command: `pnpm -C frontend-reshet test -- --runTestsByPath src/__tests__/pipeline_builder/pipeline_run_stale_executable.test.tsx --watch=false`
- Date/Time: 2026-04-01
- Result: pass (`1 suite, 1 test`)

## Known gaps or follow-ups
- Add save-error coverage for illegal write operations returned from the backend.
