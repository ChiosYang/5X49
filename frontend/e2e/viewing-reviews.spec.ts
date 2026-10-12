import { test, expect, type APIRequestContext, type Page } from '@playwright/test';
import { access, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';

test.describe.configure({ mode: 'serial' });
const backend = process.env.E2E_BACKEND!;
let filmId: string;
let timestampId: string;
const viewingsUrl = () => `${backend}/films/${filmId}/viewings`;
const read = async (request: APIRequestContext) => (await request.get(viewingsUrl())).json();
const diary = (page: Page) => page.goto(`/en/diary?film=${filmId}`);
const card = (page: Page, id: string) => page.locator('article').filter({ has: page.locator(`#viewing-link-${id}`) });
const editor = (page: Page) => page.locator('div[aria-label="Edit viewing"]');
const notes = (page: Page) => page.getByLabel("This viewing's notes", { exact: false });
async function control(request: APIRequestContext, action: string) {
  const result = await request.post(`${backend}/__e2e/control`, { headers: { 'x-e2e-token': process.env.E2E_TOKEN! }, data: { action } });
  expect(result.ok()).toBeTruthy(); return result.json();
}
test.beforeAll(async ({ request }) => {
  const fixture = await control(request, 'viewing_review_fixture');
  filmId = fixture.film_id; timestampId = fixture.viewings[2].id;
});
test.afterAll(async ({ request }) => { await control(request, 'identity_cleanup'); });
test.beforeEach(async ({ context }) => {
  await context.route('**/*', route => ['127.0.0.1', 'localhost'].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort('blockedbyclient'));
});

test('create separate reviews, cancel, close and back; existing Film score remains intact', async ({ page, request }) => {
  await page.addInitScript(() => Object.defineProperty(Crypto.prototype, 'randomUUID', { value: undefined }));
  await diary(page);
  expect((await read(request)).every((row: {rating: number | null; notes: string | null}) => row.rating === null && row.notes === null)).toBe(true);
  await page.getByRole('button', { name: 'Other date', exact: true }).click();
  await notes(page).fill('Discard this draft');
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  expect(await read(request)).toHaveLength(4);
  await page.getByRole('button', { name: 'Other date', exact: true }).click();
  await expect(notes(page)).toHaveValue('');
  await notes(page).fill('Discard when closed');
  await page.getByRole('button', { name: 'Close other date', exact: true }).click();
  expect(await read(request)).toHaveLength(4);
  await page.getByRole('button', { name: 'Other date', exact: true }).click();
  await page.getByLabel("This viewing's rating").selectOption('4');
  await notes(page).fill('First watch: a quiet surprise.');
  await page.getByRole('button', { name: 'Record', exact: true }).click();
  await expect(page.getByText('Viewing recorded.', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Close', exact: true }).click();
  await page.getByRole('button', { name: 'Other date', exact: true }).click();
  await page.getByLabel("This viewing's rating").selectOption('5');
  await notes(page).fill('On rewatch, the ending feels different.');
  await page.getByRole('button', { name: 'Record', exact: true }).click();
  await expect(page.getByText('Viewing recorded.', { exact: true })).toBeVisible();
  expect(await read(request)).toHaveLength(6);
  const profile = await (await request.get(`${backend}/films/${filmId}/profile-state`)).json();
  expect(profile).toMatchObject({ rating: 3, notes: 'Historical Film note' });
  await page.getByRole('button', { name: 'Close', exact: true }).click();
  await card(page, timestampId).getByRole('button', { name: 'Edit viewing', exact: true }).click();
  await notes(page).fill('Discard on back');
  await page.goto('/en/library'); await page.goBack();
  await expect(editor(page)).toHaveCount(0);
  expect((await read(request)).find((row: {id: string}) => row.id === timestampId).notes).toBeNull();
});

test('edit and clear preserve timestamps; all date precisions remain editable', async ({ page, request }) => {
  await diary(page);
  await card(page, timestampId).getByRole('button', { name: 'Edit viewing', exact: true }).click();
  await page.getByLabel("This viewing's rating").selectOption('2');
  await notes(page).fill('Timestamp impression');
  await editor(page).getByRole('button', { name: 'Save', exact: true }).click();
  await expect(page.getByText('Viewing updated.', { exact: true })).toBeVisible();
  let row = (await read(request)).find((item: {id: string}) => item.id === timestampId);
  expect(row).toMatchObject({ rating: 2, notes: 'Timestamp impression', watched_at: '2026-01-02T23:30:00+08:00', watched_at_precision: 'timestamp' });
  await editor(page).getByRole('button', { name: 'Close', exact: true }).click();
  await card(page, timestampId).getByRole('button', { name: 'Edit viewing', exact: true }).click();
  await page.getByLabel("This viewing's rating").selectOption(''); await notes(page).fill('');
  await editor(page).getByRole('button', { name: 'Save', exact: true }).click();
  await expect(page.getByText('Viewing updated.', { exact: true })).toBeVisible();
  row = (await read(request)).find((item: {id: string}) => item.id === timestampId);
  expect(row).toMatchObject({ rating: null, notes: null, watched_at_precision: 'timestamp' });
  for (const mode of ['Year only', 'Unknown', 'Exact date']) {
    await editor(page).getByRole('button', { name: 'Close', exact: true }).click();
    await card(page, timestampId).getByRole('button', { name: 'Edit viewing', exact: true }).click();
    if (await page.getByRole('button', { name: 'Other date options', exact: true }).count()) await page.getByRole('button', { name: 'Other date options', exact: true }).click();
    await page.getByRole('radio', { name: mode, exact: true }).check();
    if (mode === 'Year only') await page.getByLabel('Viewing year').fill('2024');
    if (mode === 'Exact date') await page.getByLabel('Viewing date', { exact: true }).fill('2026-01-03');
    await notes(page).fill(`Precision: ${mode}`);
    await editor(page).getByRole('button', { name: 'Save', exact: true }).click();
    await expect(page.getByText('Viewing updated.', { exact: true })).toBeVisible();
    row = (await read(request)).find((item: {id: string}) => item.id === timestampId);
    expect(row.watched_at_precision).toBe(mode === 'Year only' ? 'year' : mode === 'Unknown' ? 'unknown' : 'date');
  }
});

test('lost create response and 503 retries use identical requests, with one row and safe undo', async ({ page, request }) => {
  await diary(page);
  const before = await read(request);
  await page.getByRole('button', { name: 'Other date', exact: true }).click();
  await notes(page).fill('One committed retry');
  let lose = true; const bodies: string[] = [];
  await page.route(`**/api/films/${filmId}/viewings`, async route => {
    if (route.request().method() !== 'POST') return route.continue();
    bodies.push(route.request().postData()!);
    const response = await route.fetch();
    if (lose) { lose = false; return route.abort('failed'); }
    return route.fulfill({ response });
  });
  await page.getByRole('button', { name: 'Record', exact: true }).dblclick();
  await expect(page.getByRole('button', { name: 'Retry save', exact: true })).toBeVisible();
  await expect(notes(page)).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Cancel', exact: true })).toBeDisabled();
  // Even a reload after an ambiguous response resumes the original request identity.
  await page.reload();
  await expect(page.getByRole('button', { name: 'Retry save', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Retry save', exact: true }).click();
  await expect(page.getByText('Viewing recorded.', { exact: true })).toBeVisible();
  expect(bodies).toHaveLength(2); expect(bodies[0]).toBe(bodies[1]);
  expect(await read(request)).toHaveLength(before.length + 1);
  await page.getByRole('button', { name: 'Undo this new record', exact: true }).click();
  await expect(page.getByText('The new viewing was removed.', { exact: true })).toBeVisible();
  expect(await read(request)).toHaveLength(before.length);
  await page.unroute(`**/api/films/${filmId}/viewings`);
  if (await page.getByRole('button', { name: 'Close', exact: true }).count()) await page.getByRole('button', { name: 'Close', exact: true }).click();
  await card(page, timestampId).getByRole('button', { name: 'Edit viewing', exact: true }).click();
  await notes(page).fill('Recovered after server failure');
  let fail = true;
  await page.route(`**/api/viewings/${timestampId}`, route => {
    if (route.request().method() === 'PATCH' && fail) { fail = false; return route.fulfill({ status: 503, json: {detail: 'Synthetic failure'} }); }
    return route.continue();
  });
  await editor(page).getByRole('button', { name: 'Save', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Retry save', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Retry save', exact: true }).click();
  await expect(page.getByText('Viewing updated.', { exact: true })).toBeVisible();
});

test('stale open form cannot overwrite new review after background refresh', async ({ page, request }) => {
  await diary(page);
  await card(page, timestampId).getByRole('button', { name: 'Edit viewing', exact: true }).click();
  await notes(page).fill('Stale local draft');
  const original = (await read(request)).find((row: {id: string}) => row.id === timestampId);
  const response = await request.patch(`${backend}/viewings/${timestampId}`, { data: { revision: original.revision,
    watched_at: '2025-08-04', rating: 5, notes: 'Saved in another tab', idempotency_key: 'e2e-concurrent-0001' } });
  expect(response.ok()).toBeTruthy();
  // Revalidation must never update the opened form's revision behind the user's back.
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await expect(notes(page)).toHaveValue('Stale local draft');
  await editor(page).getByRole('button', { name: 'Save', exact: true }).click();
  await expect(page.getByText('This viewing changed or is no longer available.', { exact: false })).toBeVisible();
  expect((await read(request)).find((row: {id: string}) => row.id === timestampId).notes).toBe('Saved in another tab');
  let failRefresh = true;
  await page.route('**/api/profile/viewings?*', route => failRefresh ? route.fulfill({status:503,json:{detail:'Synthetic reload failure'}}) : route.continue());
  await page.getByRole('button', { name: 'Reload viewing', exact: true }).click();
  await expect(page.getByText('Could not reload this viewing.', { exact: false })).toBeVisible();
  await expect(notes(page)).toHaveValue('Stale local draft');
  failRefresh = false;
  await page.getByRole('button', { name: 'Reload viewing', exact: true }).click();
  await expect(editor(page)).toHaveCount(0);
  await card(page, timestampId).getByRole('button', { name: 'Edit viewing', exact: true }).click();
  await expect(notes(page)).toHaveValue('Saved in another tab');
  await notes(page).fill('x'.repeat(10001));
  await expect(editor(page).getByRole('button', { name: 'Save', exact: true })).toBeDisabled();
  await editor(page).getByRole('button', { name: 'Cancel', exact: true }).click();
});

test('restart persistence, detail/diary agreement, desktop and narrow Chinese evidence', async ({ page, request }) => {
  const before = await read(request);
  const root = process.env.E2E_ROOT!;
  await rm(path.join(root, 'restarted'), { force: true });
  await writeFile(path.join(root, 'restart'), 'viewing review persistence');
  await expect.poll(async () => { try { await access(path.join(root, 'restarted')); return true; } catch { return false; } }, { timeout: 30000 }).toBe(true);
  expect(await read(request)).toEqual(before);
  await rm(path.join(root, 'restarted'), { force: true });
  await page.goto(`/en/library/${filmId}`);
  await expect(page.getByText('Historical Film note', { exact: true })).toBeVisible();
  await expect(page.getByTestId('viewing-review').filter({hasText: 'First watch: a quiet surprise.'})).toBeVisible();
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.goto(`/zh/diary?film=${filmId}`);
  await expect(page.getByRole('heading', { name: '观影日记', exact: true })).toBeVisible();
  await page.screenshot({ path: path.join('e2e-artifacts', 'viewing-reviews-desktop-zh.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: path.join('e2e-artifacts', 'viewing-reviews-narrow-zh.png'), fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await card(page, timestampId).getByRole('button', { name: '修改观看记录', exact: true }).click();
  await expect(page.getByLabel('本次观看感想', { exact: false })).toHaveValue('Saved in another tab');
  await page.getByLabel('本次观看评分').selectOption('4');
  await page.getByLabel('本次观看感想', { exact: false }).fill('这一次重看，留意到了结尾里的沉默。');
  await page.getByLabel('本次观看感想', { exact: false }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join('e2e-artifacts', 'viewing-reviews-editor-narrow-zh.png') });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
