import { expect, test } from "@playwright/test"

test("settings governance smoke", async ({ page }) => {
  await page.goto("/admin/settings")

  await expect(page.getByRole("tab", { name: /People & Permissions/i })).toBeVisible()
  await page.getByRole("tab", { name: /People & Permissions/i }).click()

  await expect(page.getByText(/Members|Invitations|Groups|Roles/i)).toBeVisible()

  await page.getByRole("tab", { name: /Projects/i }).click()
  await expect(page.getByPlaceholder("Search projects by name...")).toBeVisible()

  await page.getByRole("tab", { name: /API Keys/i }).click()
  await expect(page.getByText(/Organization API Keys|Project API Keys/i)).toBeVisible()

  await page.getByRole("tab", { name: /Audit Logs/i }).click()
  await expect(page.getByText(/entries in the active organization/i)).toBeVisible()
})
