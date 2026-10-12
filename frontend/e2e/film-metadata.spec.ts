import { test, expect, type APIRequestContext } from '@playwright/test';
import { access, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';

test.describe.configure({ mode: 'serial' });
const backend = process.env.E2E_BACKEND!;
let filmId: string;
const endpoint = () => `${backend}/films/${filmId}/metadata`;
async function control(request: APIRequestContext, action: string, payload: Record<string, unknown> = {}) {
  const response = await request.post(`${backend}/__e2e/control`, { headers: { 'x-e2e-token': process.env.E2E_TOKEN! }, data: { action, ...payload } });
  expect(response.ok()).toBeTruthy(); return response.json();
}
test.beforeAll(async ({ request }) => { filmId = (await control(request, 'manual_metadata_fixture')).film_id; });
test.afterAll(async ({ request }) => { await control(request, 'identity_cleanup'); });
test.beforeEach(async ({ context }) => {
  await context.route('**/*', route => ['127.0.0.1', 'localhost'].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort('blockedbyclient'));
});

test('first edit, partial update, cancel/back, validation and protected blank year', async ({ page, request }) => {
  // Trusted LAN HTTP lacks randomUUID; saving must still generate a request key.
  await page.addInitScript(() => Object.defineProperty(Crypto.prototype, 'randomUUID', { value: undefined }));
  const before = await (await request.get(endpoint())).json();
  const profile = await (await request.get(`${backend}/films/${filmId}/profile-state`)).json();
  const viewings = await (await request.get(`${backend}/films/${filmId}/viewings`)).json();
  const identities = await (await request.get(`${backend}/library/identity-reviews?status=all`)).json();
  const nfo = (await control(request, 'manual_metadata_rescan')).nfo_digest;
  await page.goto(`/en/library/${filmId}`);
  await expect(page.getByRole('group', { name: 'Source Film, 1999', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Edit basic information', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Edit basic information' });
  await expect(dialog.getByLabel('Title', { exact: true })).toHaveValue('Source Film');
  await dialog.getByLabel('Title', { exact: true }).fill('Cancelled edit');
  await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
  expect((await (await request.get(endpoint())).json()).revision).toBe(before.revision);
  await page.getByRole('button', { name: 'Edit basic information', exact: true }).click();
  await expect(dialog.getByLabel('Title', { exact: true })).toHaveValue('Source Film');
  await dialog.getByLabel('Title', { exact: true }).fill(' ');
  await expect(dialog.getByRole('button', { name: 'Save changes' })).toBeDisabled();
  await dialog.getByLabel('Title', { exact: true }).fill('Manually Corrected Film');
  await dialog.getByLabel('Year', { exact: true }).fill('1700');
  await expect(dialog.getByText('Enter a four-digit year', { exact: false })).toBeVisible();
  await dialog.getByLabel('Year', { exact: true }).fill('');
  await dialog.getByRole('button', { name: 'Save changes' }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByText('Basic information saved.', { exact: true })).toBeVisible();
  await expect(page.getByRole('group', { name: 'Manually Corrected Film', exact: true })).toBeVisible();
  await expect(page.getByRole('group', { name: 'Source Film, 1999', exact: true })).toHaveCount(0);
  const edited = await (await request.get(endpoint())).json();
  expect(edited.fields.title.value).toBe('Manually Corrected Film');
  expect(edited.fields.year).toMatchObject({ value: null, manual: true, automatic_value: 1999 });
  expect(edited.fields.overview.manual).toBe(false);
  expect((await control(request, 'manual_metadata_rescan')).nfo_digest).toBe(nfo);
  expect(await (await request.get(`${backend}/films/${filmId}/profile-state`)).json()).toEqual(profile);
  expect(await (await request.get(`${backend}/films/${filmId}/viewings`)).json()).toEqual(viewings);
  expect(await (await request.get(`${backend}/library/identity-reviews?status=all`)).json()).toEqual(identities);
  await page.getByRole('button', { name: 'Edit basic information', exact: true }).click();
  await dialog.getByLabel('Synopsis', { exact: true }).fill('Discard on back');
  await page.goto('/en/library');
  await page.goBack();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  expect((await (await request.get(endpoint())).json()).fields.overview.value).toBe('Automatic source synopsis.');
});

test('lost save response retries the same request; repeat clicks commit once; server error retry', async ({ page, request }) => {
  await page.goto(`/en/library/${filmId}`);
  await page.getByRole('button', { name: 'Edit basic information', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Edit basic information' });
  await dialog.getByLabel('Synopsis', { exact: true }).fill('A protected manual synopsis.');
  const bodies: string[] = [];
  let lose = true;
  await page.route(`**/api/films/${filmId}/metadata`, async route => {
    if (route.request().method() !== 'PATCH') return route.continue();
    bodies.push(route.request().postData()!);
    const response = await route.fetch();
    if (lose) { lose = false; return route.abort('failed'); }
    return route.fulfill({ response });
  });
  await dialog.getByRole('button', { name: 'Save changes' }).dblclick();
  await expect(dialog.getByText('Could not confirm the save.', { exact: false })).toBeVisible();
  await expect(dialog.getByLabel('Synopsis', { exact: true })).toBeDisabled();
  await dialog.getByRole('button', { name: 'Retry save', exact: true }).click();
  await expect(dialog).toHaveCount(0);
  expect(bodies).toHaveLength(2); expect(bodies[0]).toBe(bodies[1]);
  await page.unroute(`**/api/films/${filmId}/metadata`);
  await page.getByRole('button', { name: 'Edit basic information', exact: true }).click();
  await dialog.getByLabel('Original title', { exact: true }).fill('Manual Original');
  let fail = true;
  await page.route(`**/api/films/${filmId}/metadata`, route => {
    if (route.request().method() === 'PATCH' && fail) { fail = false; return route.fulfill({ status: 503, json: { detail: { code: 'metadata_temporarily_unavailable' } } }); }
    return route.continue();
  });
  await dialog.getByRole('button', { name: 'Save changes' }).click();
  await expect(dialog.getByRole('button', { name: 'Retry save', exact: true })).toBeVisible();
  await dialog.getByRole('button', { name: 'Retry save', exact: true }).click();
  await expect(dialog).toHaveCount(0);
  expect((await (await request.get(endpoint())).json()).fields.original_title.value).toBe('Manual Original');
});

test('rescan/scrape preserve corrections; stale reset requires reviewing latest automatic data', async ({ page, request }) => {
  await page.goto(`/en/library/${filmId}`);
  await page.getByRole('button', { name: 'Edit basic information', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Edit basic information' });
  await dialog.getByRole('button', { name: 'Restore automatic source for Year' }).click();
  const scan = await control(request, 'manual_metadata_rescan', { change_source: true });
  expect(scan.film.title).toBe('Manually Corrected Film'); expect(scan.film.year).toBeNull();
  await dialog.getByRole('button', { name: 'Save changes' }).click();
  await expect(dialog.getByText('The film or its automatic data changed.', { exact: false })).toBeVisible();
  await expect(dialog.getByRole('button', { name: 'Save changes' })).toBeDisabled();
  await dialog.getByRole('button', { name: 'Reload current values' }).click();
  await expect(dialog.getByLabel('Year', { exact: true })).toHaveValue('');
  await dialog.getByRole('button', { name: 'Restore automatic source for Year' }).click();
  await expect(dialog.getByLabel('Year', { exact: true })).toHaveValue('2001');
  await dialog.getByRole('button', { name: 'Save changes' }).click();
  await expect(dialog).toHaveCount(0);
  const scrape = await request.post(`${backend}/films/${filmId}/scrape/confirm?tmdb_id=900101`, { data: { write_nfo: false, download_artwork: false } });
  expect(scrape.ok()).toBeTruthy();
  const view = await (await request.get(endpoint())).json();
  expect(view.fields.title.value).toBe('Manually Corrected Film');
  expect(view.fields.overview.value).toBe('A protected manual synopsis.');
  expect(view.fields.year.manual).toBe(false);
  expect((await control(request, 'manual_metadata_rescan')).nfo_digest).toBe(scan.nfo_digest);
});

test('real process restart retains manual data; desktop and narrow Chinese evidence', async ({ page, request }) => {
  const before = await (await request.get(endpoint())).json();
  const root = process.env.E2E_ROOT!;
  await rm(path.join(root, 'restarted'), { force: true });
  await writeFile(path.join(root, 'restart'), 'manual metadata persistence');
  await expect.poll(async () => { try { await access(path.join(root, 'restarted')); return true; } catch { return false; } }, { timeout: 30000 }).toBe(true);
  expect(await (await request.get(endpoint())).json()).toEqual(before);
  await rm(path.join(root, 'restarted'), { force: true });
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.goto(`/zh/library/${filmId}`);
  await page.getByRole('button', { name: '编辑基础资料', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '编辑基础资料' });
  await expect(dialog.getByLabel('标题', { exact: true })).toHaveValue('Manually Corrected Film');
  await dialog.getByText('查看自动值', { exact: false }).first().click();
  await page.screenshot({ path: path.join('e2e-artifacts', 'manual-metadata-desktop-zh.png') });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(dialog).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: path.join('e2e-artifacts', 'manual-metadata-narrow-zh.png') });
  await dialog.getByRole('button', { name: '保存修改' }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join('e2e-artifacts', 'manual-metadata-narrow-save-zh.png') });
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole('button', { name: '编辑基础资料', exact: true })).toBeFocused();
});

test('a stalled initial read can be cancelled and reopened without writing', async ({ page, request }) => {
  const before = await (await request.get(endpoint())).json();
  await page.goto(`/en/library/${filmId}`);
  await expect(page.getByRole('button', { name: 'Edit basic information', exact: true })).toBeVisible();
  let unblock!: () => void;
  const blocked = new Promise<void>(resolve => { unblock = resolve; });
  await page.route(`**/api/films/${filmId}/metadata`, async route => { await blocked; await route.continue().catch(() => {}); });
  await page.getByRole('button', { name: 'Edit basic information', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Edit basic information' });
  await expect(dialog.getByRole('status')).toBeVisible();
  await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(dialog).toHaveCount(0);
  unblock();
  await page.unroute(`**/api/films/${filmId}/metadata`);
  await page.getByRole('button', { name: 'Edit basic information', exact: true }).click();
  await expect(dialog.getByLabel('Title', { exact: true })).toHaveValue(before.fields.title.value);
  await page.keyboard.press('Escape');
  expect(await (await request.get(endpoint())).json()).toEqual(before);
});
