import { expect, type Locator } from '@playwright/test';

export async function expectAnnouncedOnly(status: Locator, message: string) {
  await expect(status).toHaveText(message);
  await expect(status).toHaveAttribute('role', 'status');
  await expect(status).toHaveAttribute('aria-live', 'polite');
  await expect(status).toHaveCSS('overflow', 'hidden');
  const bounds = (await status.boundingBox())!;
  expect(bounds.width).toBeLessThanOrEqual(1);
  expect(bounds.height).toBeLessThanOrEqual(1);
}
