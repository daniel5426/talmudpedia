# Settings Governance Browser Smoke Test State

Last Updated: 2026-04-19

## Scope
Minimal Playwright smoke for the canonical `/admin/settings` governance surface.

## Test Files
- `settings-smoke.spec.ts`

## Key Scenarios Covered
- load `/admin/settings`
- switch to `People & Permissions`
- switch to `Projects`
- switch to `API Keys`
- switch to `Audit Logs`

## Last Run
- Command: `pnpm -C frontend-reshet test:e2e -- e2e/settings-smoke.spec.ts`
- Date: 2026-04-19
- Result: Blocked by local auth proxy dependency (`/admin/settings` redirected to `/api/py/auth/login`, and proxy target `http://localhost:8026/auth/login` refused connection)

## Known Gaps
- No authenticated browser seed or auth bypass is configured for local Playwright runs yet.
