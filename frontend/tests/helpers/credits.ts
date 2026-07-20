import { expect, type Page } from "@playwright/test";

/**
 * Confirm a credit-gated action when its cost requires explicit approval.
 * Low-cost actions execute inline and never render this dialog.
 */
export async function confirmCreditCostIfShown(page: Page): Promise<boolean> {
  const confirm = page.getByTestId("credit-confirm");
  if (!(await confirm.isVisible().catch(() => false))) return false;
  await expect(page.getByRole("dialog")).toContainText(/charged only when/i);
  await confirm.click();
  return true;
}

/** Start an explicit draft-email generation after its no-charge preview opens. */
export async function generateDraftFromPreview(page: Page): Promise<void> {
  const button = page.getByTestId("generate-draft-button");
  await expect(button).toBeVisible();
  await button.click();
  await confirmCreditCostIfShown(page);
}
