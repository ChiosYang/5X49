import { test, expect, type APIRequestContext } from '@playwright/test';
import path from 'node:path';

test.describe.configure({ mode: 'serial' });
const backend = process.env.E2E_BACKEND!;
let fixture: { review_id: string; candidate_item_id: string; film_id: string };
async function control(request: APIRequestContext, action: string, payload: Record<string, unknown> = {}) {
  const result = await request.post(`${backend}/__e2e/control`, {
    headers: { 'x-e2e-token': process.env.E2E_TOKEN! }, data: { action, ...payload },
  });
  expect(result.ok()).toBeTruthy();
  return result.json();
}

test.beforeAll(async ({ request }) => { fixture = await control(request, 'identity_fixtures'); });
test.afterAll(async ({ request }) => {
  await control(request, 'identity_cleanup');
  const result = await request.put(`${backend}/settings/media-dir`, {
    params: { media_dir: path.join(process.env.E2E_ROOT!, 'empty') },
  });
  expect(result.ok()).toBeTruthy();
});
test.beforeEach(async ({ context }) => {
  await context.route('**/*', route => ['127.0.0.1', 'localhost'].includes(new URL(route.request().url()).hostname)
    ? route.continue() : route.abort('blockedbyclient'));
});

test('real queue: repeated inspection, close, escape, back and personal data retention', async ({ page, request }) => {
  const before = await (await request.get(`${backend}/films/${fixture.film_id}/profile-state`)).json();
  const viewings = await (await request.get(`${backend}/films/${fixture.film_id}/viewings`)).json();
  const writes: string[] = [];
  page.on('request', r => { if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(r.method()) && r.url().includes('/api/')) writes.push(r.url()); });
  await page.goto('/en/library');
  await page.getByRole('link', { name: 'Identity review', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Identity review', exact: true })).toBeVisible();
  const row = page.getByRole('listitem').filter({ hasText: 'Identity copy' });
  const inspect = row.getByRole('button', { name: 'Inspect conflict' });
  await inspect.click();
  const dialog = page.getByRole('dialog', { name: 'Conflict details' });
  await expect(dialog.getByText('1 viewing records', { exact: false })).toBeVisible();
  await expect(dialog.getByText('Stored candidate records are unchanged.', { exact: false })).toBeVisible();
  await expect(dialog.getByText('Identity private notes', { exact: true })).toHaveCount(0);
  await page.screenshot({ path: path.join('e2e-artifacts', 'identity-review-mobile.png'), fullPage: true });
  await dialog.getByRole('button', { name: 'Close', exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(inspect).toBeFocused();
  await inspect.click();
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  await page.getByRole('link', { name: 'Back to library' }).click();
  await expect(page).toHaveURL(/\/en\/library$/);
  await page.goBack();
  await expect(page.getByRole('heading', { name: 'Identity review', exact: true })).toBeVisible();
  expect(await (await request.get(`${backend}/films/${fixture.film_id}/profile-state`)).json()).toEqual(before);
  expect(await (await request.get(`${backend}/films/${fixture.film_id}/viewings`)).json()).toEqual(viewings);
  expect(writes).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test('list and detail errors recover and remain closable', async ({ page }) => {
  await page.route('**/api/library/identity-reviews?*', route => route.fulfill({ status: 503, json: { detail: 'unavailable' } }));
  await page.goto('/en/library/identity-review');
  await expect(page.getByText('Could not load reviews. Please try again.')).toBeVisible();
  await page.unroute('**/api/library/identity-reviews?*');
  await page.getByRole('button', { name: 'Retry' }).click();
  await expect(page.getByText('2 pending reviews')).toBeVisible();
  await page.route(`**/api/library/identity-reviews/${fixture.review_id}`, route => route.fulfill({ status: 404, json: { detail: 'missing' } }));
  await page.getByRole('listitem').filter({ hasText: 'Identity copy' }).getByRole('button').click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByText('Could not load reviews. Please try again.')).toBeVisible();
  await dialog.getByRole('button', { name: 'Close', exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await page.unroute(`**/api/library/identity-reviews/${fixture.review_id}`);
});

test('legacy evidence and changed candidate are explicit; Chinese desktop screenshot', async ({ page, request }) => {
  await control(request, 'identity_candidate_changed', { library_item_id: fixture.candidate_item_id });
  await page.goto('/en/library/identity-review');
  await page.getByRole('listitem').filter({ hasText: 'Record unavailable' }).getByRole('button').click();
  await expect(page.getByRole('dialog').getByText('This historical review did not retain its candidates.', { exact: false })).toBeVisible();
  await page.keyboard.press('Escape');
  await page.getByRole('listitem').filter({ hasText: 'Identity copy' }).getByRole('button').click();
  await expect(page.getByRole('dialog').getByText('The candidate record has changed since this review was created.', { exact: false })).toBeVisible();
  await page.keyboard.press('Escape');
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.goto('/zh/library/identity-review');
  await expect(page.getByRole('heading', { name: '身份复核', exact: true })).toBeVisible();
  await page.getByRole('listitem').filter({ hasText: 'Identity copy' }).getByRole('button').click();
  await expect(page.getByRole('dialog').getByText('候选记录自复核创建后已改变，原始匹配已不可靠。')).toBeVisible();
  await page.screenshot({ path: path.join('e2e-artifacts', 'identity-review-desktop-zh.png'), fullPage: true });
});

test('keep independent: cancel preview and recover a lost confirmation with the same key', async ({ page, request }) => {
  await control(request, 'identity_decision_fixtures');
  // The test root contains the synthetic media; production guards must use it.
  const settings = await request.put(`${backend}/settings/media-dir`, { params: { media_dir: process.env.E2E_ROOT! } });
  expect(settings.ok()).toBeTruthy();
  await page.goto('/en/library/identity-review');
  const row = page.getByRole('listitem').filter({ hasText: 'Decision copy' });
  await row.getByRole('button', { name: 'Inspect conflict' }).click();
  let dialog = page.getByRole('dialog');
  await dialog.getByRole('button', { name: 'Keep independent edition' }).click();
  await expect(dialog.getByRole('region', { name: 'Confirm decision' })).toBeVisible();
  await dialog.getByRole('button', { name: 'Back to comparison' }).click();
  await expect(dialog.getByRole('region', { name: 'Confirm decision' })).toHaveCount(0);
  await dialog.getByRole('button', { name: 'Keep independent edition' }).click();
  const confirmations: string[] = [];
  await page.route('**/api/library/identity-reviews/*/confirm', async route => {
    confirmations.push(route.request().postData()!);
    if (confirmations.length === 1) { await route.fetch(); await route.abort('failed'); }
    else await route.continue();
  });
  await dialog.getByRole('button', { name: 'Confirm decision', exact: true }).click({ clickCount: 2 });
  await expect(dialog.getByRole('alert')).toBeVisible();
  await dialog.getByRole('button', { name: 'Confirm decision', exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole('status').filter({ hasText: 'Decision saved.' })).toBeVisible();
  expect(confirmations).toHaveLength(2);
  expect(confirmations[0]).toBe(confirmations[1]);
  await expect(row).toHaveCount(0);
  await page.unroute('**/api/library/identity-reviews/*/confirm');
  dialog = page.getByRole('dialog');
  await expect(dialog).toHaveCount(0);
});

test('same-film reconnect rejects live original then preserves personal records on confirmation', async ({ page, request }) => {
  const reviews = await (await request.get(`${backend}/library/identity-reviews`)).json();
  const review = reviews.items.find((r: { film: { title: string } | null }) => r.film?.title === 'Reconnect discovery');
  expect(review).toBeTruthy();
  const before = await (await request.get(`${backend}/films/${review.film.id}/profile-state`)).json();
  const viewings = await (await request.get(`${backend}/films/${review.film.id}/viewings`)).json();
  await page.goto('/en/library/identity-review');
  await page.getByRole('listitem').filter({ hasText: 'Reconnect discovery' }).getByRole('button', { name: 'Inspect conflict' }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('button', { name: 'Reconnect to this edition' }).click();
  await expect(dialog.getByRole('alert')).toContainText('The old file still exists.');
  await control(request, 'identity_old_disappeared');
  await dialog.getByRole('button', { name: 'Reconnect to this edition' }).click();
  await expect(dialog.getByRole('region', { name: 'Confirm decision' })).toContainText('Retain the new discovery as a retired history record.');
  await expect(dialog.getByRole('region', { name: 'Confirm decision' })).toContainText('1 earlier undo actions');
  await dialog.getByRole('region', { name: 'Confirm decision' }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join('e2e-artifacts', 'identity-reconnect-confirm.png') });
  await dialog.getByRole('button', { name: 'Confirm decision', exact: true }).click();
  await expect(dialog).toHaveCount(0);
  expect(await (await request.get(`${backend}/films/${review.film.id}/profile-state`)).json()).toEqual(before);
  expect(await (await request.get(`${backend}/films/${review.film.id}/viewings`)).json()).toEqual(viewings);
  const result = await (await request.get(`${backend}/library/identity-reviews/${review.id}`)).json();
  expect(result.status).toBe('resolved');
  await expect(page.getByRole('listitem').filter({ hasText: 'Reconnect discovery' })).toHaveCount(0);
});
