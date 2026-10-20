import { test, expect, type APIRequestContext } from '@playwright/test';
import { access, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';
import type { LibraryFilmSummary } from '../src/types/movie';

test.describe.configure({ mode: 'serial' });
const backend = process.env.E2E_BACKEND!;
const root = process.env.E2E_ROOT!;
let roots: string[], filmId: string, editionIds: string[], artwork: string;
let profile: unknown, viewings: unknown;
async function read(request: APIRequestContext, url: string) {
  const response = await request.get(`${backend}${url}`);
  expect(response.ok()).toBeTruthy(); return response.json();
}
async function control(request: APIRequestContext, action: string) {
  const response = await request.post(`${backend}/__e2e/control`, { headers: { 'x-e2e-token': process.env.E2E_TOKEN! }, data: { action } });
  expect(response.ok()).toBeTruthy(); return response.json();
}
async function scan(request: APIRequestContext) {
  const response = await request.post(`${backend}/library/scan`);
  expect(response.ok()).toBeTruthy();
  const id = (await response.json()).workflow_id;
  await expect.poll(async () => (await read(request, `/workflows/${id}`)).status, { timeout: 45000 }).toBe('succeeded');
  return (await read(request, '/library/sync/status')).sync.last_result;
}
async function multiFilms(request: APIRequestContext) {
  const result = await read(request, '/library/films');
  return result.filter((film: LibraryFilmSummary) => ['982000', '982001', '982002'].includes(String(film.identities.tmdb))) as LibraryFilmSummary[];
}
test.beforeAll(async ({ request }) => { roots = (await control(request, 'multi_root_fixture')).roots; });
test.beforeEach(async ({ context }) => {
  await context.route('**/*', route => ['127.0.0.1', 'localhost'].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort('blockedbyclient'));
});

test('configure ordered roots in UI, reject overlap, scan root and nested files; desktop pixels', async ({ page, request }) => {
  expect((await request.put(`${backend}/settings/media-dirs`, { data: { media_dirs: [roots[0]] } })).ok()).toBeTruthy();
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.goto('/en/settings?section=library');
  const panel = page.getByLabel('Media directories', { exact: true });
  await panel.getByRole('button', { name: 'Add', exact: true }).click();
  await page.locator('#media-root-1').fill(path.join(roots[0], 'country'));
  await panel.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(panel.getByText('A parent and its child cannot both be media roots.', { exact: false })).toBeVisible();
  expect((await read(request, '/settings/media-dirs')).media_dirs).toEqual([roots[0]]);
  await page.locator('#media-root-1').fill(roots[1]);
  await panel.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(panel.getByText('Configuration saved.', { exact: false })).toBeVisible();
  expect(await multiFilms(request)).toHaveLength(0);
  const queued = page.waitForResponse(r => r.url().endsWith('/api/library/scan') && r.request().method() === 'POST');
  await panel.getByRole('button', { name: 'Scan all directories' }).click();
  const id = (await (await queued).json()).workflow_id;
  await expect.poll(async () => (await read(request, `/workflows/${id}`)).status).toBe('succeeded');
  const result = (await read(request, '/library/sync/status')).sync.last_result;
  expect(result.complete).toBe(true); expect(result.scanned).toBe(3);
  const films = await multiFilms(request); expect(films).toHaveLength(3);
  filmId = films[0].id;
  editionIds = films.map((film: { primary_item: { id: string } }) => film.primary_item.id).sort();
  artwork = films.find(film => String(film.identities.tmdb) === '982002')!.primary_item.artwork.poster_local!;
  expect((await request.get(`${backend}${artwork}`)).ok()).toBeTruthy();
  await expect(panel.getByText(/^Complete scan · Scanned 3/)).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: 'e2e-artifacts/media-roots-desktop-en.png', fullPage: true });
});

test('repeat scan keeps manual metadata, Film review, Viewing review and combined filters', async ({ request }) => {
  const metadata = await read(request, `/films/${filmId}/metadata`);
  const changed = await request.patch(`${backend}/films/${filmId}/metadata`, { data: { revision: metadata.revision, changes: { title: { action: 'set', value: 'Multi Personal Title' } }, idempotency_key: 'multi-root-manual-0001' } });
  expect(changed.ok()).toBeTruthy();
  expect((await request.put(`${backend}/films/${filmId}/profile-state`, { data: { favorite: true, rating: 4, notes: 'Multi Film review' } })).ok()).toBeTruthy();
  expect((await request.post(`${backend}/films/${filmId}/viewings`, { data: { watched_at: '2026', rating: 5, notes: 'Multi Viewing review', idempotency_key: 'multi-root-viewing-0001' } })).ok()).toBeTruthy();
  profile = await read(request, `/films/${filmId}/profile-state`);
  viewings = await read(request, `/films/${filmId}/viewings`);
  const result = await scan(request); expect(result.added).toBe(0); expect(result.missing).toBe(0);
  expect((await multiFilms(request)).map((film: { primary_item: { id: string } }) => film.primary_item.id).sort()).toEqual(editionIds);
  expect((await read(request, `/library/films/${filmId}`)).title).toBe('Multi Personal Title');
  expect(await read(request, `/films/${filmId}/profile-state`)).toEqual(profile);
  expect(await read(request, `/films/${filmId}/viewings`)).toEqual(viewings);
  const filtered = await read(request, '/library/films/page?q=Multi%20Personal&favorite=true&rating_min=4&year_min=2000');
  expect(filtered.items.map((film: { id: string }) => film.id)).toEqual([filmId]);
});

test('offline root produces incomplete coverage without missing editions; narrow pixels', async ({ page, request }) => {
  await control(request, 'multi_root_offline');
  const result = await scan(request);
  expect(result.complete).toBe(false); expect(result.missing).toBe(0);
  expect(result.roots[1].state).toBe('offline');
  expect(await multiFilms(request)).toHaveLength(3);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/zh/settings?section=library');
  await expect(page.locator('#media-root-1')).toHaveValue(roots[1]);
  await page.getByRole('button', { name: '扫描全部目录' }).scrollIntoViewIfNeeded();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: 'e2e-artifacts/media-roots-offline-narrow-zh.png', fullPage: true });
  await control(request, 'multi_root_online');
});

test('legacy first-root setting preserves other roots; removal revokes old media and preserves records', async ({ request }) => {
  expect((await request.put(`${backend}/settings/media-dir`, { params: { media_dir: roots[0] } })).ok()).toBeTruthy();
  expect((await read(request, '/settings/media-dirs')).media_dirs).toEqual(roots);
  expect((await request.put(`${backend}/settings/media-dirs`, { data: { media_dirs: [roots[0]] } })).ok()).toBeTruthy();
  expect((await request.get(`${backend}${artwork}`)).status()).toBe(404);
  expect((await scan(request)).missing).toBe(0);
  expect(await multiFilms(request)).toHaveLength(3);
  expect(await read(request, `/films/${filmId}/profile-state`)).toEqual(profile);
  expect(await read(request, `/films/${filmId}/viewings`)).toEqual(viewings);
});

test('restart preserves ordered configuration and receipts; empty list disables scans and access', async ({ page, request }) => {
  expect((await request.put(`${backend}/settings/media-dirs`, { data: { media_dirs: roots } })).ok()).toBeTruthy();
  await scan(request);
  await rm(path.join(root, 'restarted'), { force: true });
  await writeFile(path.join(root, 'restart'), 'multi-root persistence');
  await expect.poll(async () => { try { await access(path.join(root, 'restarted')); return true; } catch { return false; } }, { timeout: 30000 }).toBe(true);
  expect((await read(request, '/settings/media-dirs')).media_dirs).toEqual(roots);
  expect((await read(request, '/library/sync/status')).sync.last_result.complete).toBe(true);
  expect((await scan(request)).added).toBe(0);
  expect(await read(request, `/films/${filmId}/viewings`)).toEqual(viewings);
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.goto('/zh/library/manage');
  await page.getByRole('button', { name: '扫描全部目录' }).scrollIntoViewIfNeeded();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: 'e2e-artifacts/media-roots-manage-desktop-zh.png', fullPage: true });
  expect((await request.put(`${backend}/settings/media-dirs`, { data: { media_dirs: [] } })).ok()).toBeTruthy();
  expect((await request.post(`${backend}/library/scan`)).status()).toBe(400);
  expect((await request.get(`${backend}${artwork}`)).status()).toBe(404);
  expect(await multiFilms(request)).toHaveLength(3);
});
