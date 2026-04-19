# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: settings-smoke.spec.ts >> settings governance smoke
- Location: e2e/settings-smoke.spec.ts:3:5

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByRole('tab', { name: /People & Permissions/i })
Expected: visible
Timeout: 5000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 5000ms
  - waiting for getByRole('tab', { name: /People & Permissions/i })
    - waiting for" http://127.0.0.1:3000/api/py/auth/login?return_to=%2Fadmin%2Fsettings" navigation to finish...
    - navigated to "http://127.0.0.1:3000/api/py/auth/login?return_to=%2Fadmin%2Fsettings"

```

# Page snapshot

```yaml
- generic [ref=e2]: Internal Server Error
```

# Test source

```ts
  1  | import { expect, test } from "@playwright/test"
  2  | 
  3  | test("settings governance smoke", async ({ page }) => {
  4  |   await page.goto("/admin/settings")
  5  | 
> 6  |   await expect(page.getByRole("tab", { name: /People & Permissions/i })).toBeVisible()
     |                                                                          ^ Error: expect(locator).toBeVisible() failed
  7  |   await page.getByRole("tab", { name: /People & Permissions/i }).click()
  8  | 
  9  |   await expect(page.getByText(/Members|Invitations|Groups|Roles/i)).toBeVisible()
  10 | 
  11 |   await page.getByRole("tab", { name: /Projects/i }).click()
  12 |   await expect(page.getByPlaceholder("Search projects by name...")).toBeVisible()
  13 | 
  14 |   await page.getByRole("tab", { name: /API Keys/i }).click()
  15 |   await expect(page.getByText(/Organization API Keys|Project API Keys/i)).toBeVisible()
  16 | 
  17 |   await page.getByRole("tab", { name: /Audit Logs/i }).click()
  18 |   await expect(page.getByText(/entries in the active organization/i)).toBeVisible()
  19 | })
  20 | 
```