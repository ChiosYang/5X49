import { test, expect, type APIRequestContext } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import path from 'node:path';

const backend = process.env.E2E_BACKEND!;
async function read(request: APIRequestContext, url: string) {
  const response = await request.get(`${backend}${url}`);
  expect(response.ok()).toBeTruthy();
  return response.json();
}

test('confirmed production reset handles merged aliases and permits scanning the same media again', async ({ page, request, context }) => {
  await context.route('**/*', route => ['127.0.0.1', 'localhost'].includes(new URL(route.request().url()).hostname)
    ? route.continue() : route.abort('blockedbyclient'));
  // This suite runs on run.mjs's owned disposable database and media root.
  expect((await request.delete(`${backend}/library/data`)).ok()).toBeTruthy();
  const fixtureResponse = await request.post(`${backend}/__e2e/control`, {
    headers: { 'x-e2e-token': process.env.E2E_TOKEN! }, data: { action: 'deep_reset_fixture' },
  });
  expect(fixtureResponse.ok()).toBeTruthy();
  const fixture = await fixtureResponse.json();
  expect(fixture.aliases).toBe(2);
  expect((await request.put(`${backend}/settings/media-dirs`, { data: { media_dirs: [fixture.media] } })).ok()).toBeTruthy();
  const settings = await read(request, '/settings/media-dirs');
  const backup = await read(request, '/maintenance/backups');
  const media = path.join(fixture.media, 'B alias', 'film.mkv');
  const nfo = path.join(fixture.media, 'B alias', 'film.nfo');
  const files = [await readFile(media), await readFile(nfo)];
  await page.goto('/en/settings?section=library#danger-zone');
  await page.getByRole('button', { name: 'Clear Data', exact: true }).click();
  const dialog = page.getByRole('dialog');
  const confirm = dialog.getByRole('button', { name: 'Permanently Clear Data', exact: true });
  await expect(confirm).toBeDisabled();
  await dialog.locator('input').fill('CLEAR');
  await expect(confirm).toBeDisabled();
  await dialog.locator('input').fill('CLEAR ALL DATA');
  const cleared = page.waitForResponse(response => response.request().method() === 'DELETE' && response.url().endsWith('/api/library/data'));
  await confirm.click();
  const response = await cleared;
  expect(response.ok()).toBeTruthy();
  expect((await response.json()).deleted).toMatchObject({ films: 3, library_items: 3 });
  await expect(dialog).not.toBeVisible();
  expect(await read(request, '/library/films')).toEqual([]);
  expect(await read(request, '/settings/media-dirs')).toEqual(settings);
  expect(await read(request, '/maintenance/backups')).toEqual(backup);
  expect([await readFile(media), await readFile(nfo)]).toEqual(files);
  const scan = await request.post(`${backend}/library/scan`);
  expect(scan.ok()).toBeTruthy();
  const id = (await scan.json()).workflow_id;
  await expect.poll(async () => (await read(request, `/workflows/${id}`)).status, { timeout: 45000 }).toBe('succeeded');
  expect((await read(request, '/library/sync/status')).sync.last_result.complete).toBe(true);
  expect((await read(request, '/library/films')).length).toBe(1);
  await page.goto('/en/library');
  await expect(page.locator('main').first()).toContainText(/A target|B alias|C alias/);
});
