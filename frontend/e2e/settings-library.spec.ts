import { test, expect, type APIRequestContext, type Page } from '@playwright/test';
import en from '../messages/en.json';
import zh from '../messages/zh.json';
import path from 'node:path';
import type { HealthConfig } from '../src/lib/video-health';

const backend = process.env.E2E_BACKEND!;
const health = `${backend}/maintenance/video-health`;
const schedule = { enabled: true, paused: true, start_minute: 127, end_minute: 233, daily_budget_minutes: 7 };
let roots: string[], originalRoots: string[], originalHealth: HealthConfig;
async function read(request: APIRequestContext, url: string) {
  const response = await request.get(url);
  expect(response.ok()).toBeTruthy();
  return response.json();
}
async function put(request: APIRequestContext, url: string, data: object) {
  expect((await request.put(url, { data })).ok()).toBeTruthy();
}
async function selectOtherRoot(page: Page, copy: typeof en, target: string) {
  const dialog = page.getByRole('dialog', { name: copy.FileBrowser.title, exact: true });
  await dialog.getByRole('button', { name: copy.FileBrowser.up }).click();
  await dialog.getByText(path.basename(target), { exact: true }).click();
  await expect(dialog.getByText(target, { exact: true })).toBeVisible();
  await dialog.getByRole('button', { name: copy.FileBrowser.selectCurrent, exact: true }).click();
}
test.beforeAll(async ({ request }) => {
  originalRoots = (await read(request, `${backend}/settings/media-dirs`)).media_dirs;
  const { enabled, paused, start_minute, end_minute, daily_budget_minutes } = (await read(request, health)).config;
  originalHealth = { enabled, paused, start_minute, end_minute, daily_budget_minutes };
  const response = await request.post(`${backend}/__e2e/control`, {
    headers: { 'x-e2e-token': process.env.E2E_TOKEN! }, data: { action: 'multi_root_fixture' },
  });
  expect(response.ok()).toBeTruthy();
  roots = (await response.json()).roots;
});
test.afterAll(async ({ request }) => {
  await put(request, `${backend}/settings/media-dirs`, { media_dirs: originalRoots });
  await put(request, `${health}/config`, originalHealth);
});
test.beforeEach(async ({ context, request }) => {
  await put(request, `${backend}/settings/media-dirs`, { media_dirs: [roots[0]] });
  await put(request, `${health}/config`, schedule);
  await context.route('**/*', route => ['127.0.0.1', 'localhost'].includes(new URL(route.request().url()).hostname)
    ? route.continue() : route.abort('blockedbyclient'));
});

for (const locale of ['en', 'zh'] as const) {
  const copy = locale === 'en' ? en : zh;
  for (const width of [1440, 390, 320]) {
    test(`${locale} compact Library settings, keyboard icons and draft-only roots at ${width}px`, async ({ page, request }) => {
      const writes: string[] = [];
      page.on('request', req => { if (req.method() !== 'GET' && req.url().includes('/api/')) writes.push(req.url()); });
      await page.setViewportSize({ width, height: 1000 });
      await page.goto(`/${locale}/settings?section=library`);
      const panel = page.getByLabel(copy.MediaRoots.title, { exact: true });
      await expect(page.getByLabel(copy.MediaRoots.directory.replace('{number}', '1'), { exact: true })).toHaveValue(roots[0]);
      await page.evaluate(() => document.fonts.ready);
      for (const text of [copy.Settings.librarySource, copy.Settings.librarySourceDesc, copy.MediaRoots.configuration,
        copy.MediaRoots.help, copy.MediaRoots.primary, copy.MediaRoots.removal, copy.MediaRoots.docker,
        copy.Settings.artworkLanguageDesc, copy.Settings.advancedLibraryDesc, copy.VideoHealth.description,
        copy.VideoHealth.scheduleHelp, copy.VideoHealth.limits, copy.VideoHealth.loadObservable,
        copy.VideoHealth.loadLimited, copy.LibraryCare.danger.description]) {
        await expect(page.getByText(text, { exact: true })).toHaveCount(0);
      }
      await expect(panel.getByRole('button', { name: copy.MediaRoots.browse, exact: true })).toHaveCount(0);
      await expect(panel.getByRole('button', { name: copy.MediaRoots.remove, exact: true })).toHaveCount(0);
      const status = panel.getByRole('img', { name: copy.MediaRoots.accessible, exact: true });
      const tooltip = page.locator('#media-root-status-0');
      await expect(tooltip).toBeHidden();
      await status.focus();
      await expect(tooltip).toBeVisible();
      await expect(tooltip).toHaveText(copy.MediaRoots.accessible);
      await page.keyboard.press('Tab');
      const remove = panel.getByRole('button', { name: copy.MediaRoots.removeDirectory.replace('{number}', '1'), exact: true });
      await expect(remove).toBeFocused();
      expect(await remove.textContent()).toBe('');
      const inputBounds = await page.locator('#media-root-0').boundingBox();
      const removeBounds = await remove.boundingBox();
      expect(inputBounds && removeBounds && removeBounds.x >= inputBounds.x && removeBounds.x + removeBounds.width <= inputBounds.x + inputBounds.width).toBeTruthy();
      const add = panel.getByRole('button', { name: copy.MediaRoots.addDirectory, exact: true });
      await add.focus(); await expect(page.locator('#add-directory-tooltip')).toBeVisible();
      await page.keyboard.press('Space');
      const picker = page.getByRole('dialog', { name: copy.FileBrowser.title, exact: true });
      await expect(picker).toBeVisible(); await expect(page.locator('#media-root-1')).toHaveCount(0);
      await expect(panel.getByRole('button', { name: copy.MediaRoots.save, exact: true })).toHaveCount(0);
      await expect(panel.getByRole('button', { name: copy.MediaRoots.add, exact: true })).toHaveCount(0);
      await picker.getByRole('button', { name: copy.FileBrowser.cancel, exact: true }).click();
      await expect(add).toBeFocused();
      await page.locator('#media-root-0').fill('  '); await page.locator('#media-root-0').press('Tab');
      await expect(page.locator('#media-root-0')).toHaveValue(roots[0]);
      expect((await read(request, `${backend}/settings/media-dirs`)).media_dirs).toEqual([roots[0]]);
      await expect(panel.getByRole('button', { name: copy.MediaRoots.discard, exact: true })).toHaveCount(0);

      const video = page.locator('section[aria-labelledby="video-health-settings"]');
      await expect(video.locator('input[type="time"], input[type="number"], input[type="checkbox"], dl')).toHaveCount(0);
      await expect(video.getByRole('button', { name: copy.VideoHealth.save, exact: true })).toHaveCount(0);
      const toggle = video.getByRole('switch', { name: copy.VideoHealth.automatic, exact: true });
      await expect(toggle).toHaveAttribute('aria-checked', 'true');
      const autoScan = page.getByRole('switch', { name: copy.Settings.autoScan, exact: true });
      for (const property of ['width', 'height']) expect(await toggle.evaluate((element, key) => getComputedStyle(element).getPropertyValue(key), property))
        .toBe(await autoScan.evaluate((element, key) => getComputedStyle(element).getPropertyValue(key), property));
      const row = await toggle.locator('..').boundingBox(), control = await toggle.boundingBox();
      expect(row && control && control.x + control.width >= row.x + row.width - 1).toBeTruthy();
      for (const button of await video.getByRole('button').all()) {
        expect(await button.evaluate(element => element.getBoundingClientRect().right <= element.parentElement!.getBoundingClientRect().right + 1)).toBe(true);
      }
      await expect(video.getByRole('link', { name: copy.VideoHealth.maintenanceLink, exact: true })).toHaveAttribute('href', `${locale === 'zh' ? '' : '/en'}/settings?section=video-checks#video-health`);
      await expect(page.getByText(copy.Settings.autoOrganizeRootDesc, { exact: true })).toBeVisible();
      await expect(page.getByText(copy.Settings.notWatching, { exact: true })).toHaveCount(0);
      await expect(page.getByText(copy.VideoHealth.automaticDescription, { exact: true })).toBeVisible();
      await expect(page.getByText(copy.Settings.scrapeRequireConfirmationDesc, { exact: true })).toBeVisible();
      await expect(page.locator('#danger-zone')).toHaveCount(0);
      await expect(video.getByRole('button', { name: copy.VideoHealth.queue, exact: true })).toHaveCount(0);
      await page.evaluate(() => window.scrollTo(0, 0));
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: `e2e-artifacts/settings-library-${locale}-${width}.png`, fullPage: true, animations: 'disabled' });
      expect(writes).toEqual([]);
    });
  }

  test(`${locale} roots picker autosaves, retains failed drafts, preserves append order and retries removal`, async ({ page, request }) => {
    await page.goto(`/${locale}/settings?section=library`);
    const panel = page.getByLabel(copy.MediaRoots.title, { exact: true });
    let reject = true;
    await page.route('**/api/settings/media-dirs', route => route.request().method() === 'PUT' && reject
      ? route.fulfill({ status: 503, json: { detail: 'E2E unavailable' } }) : route.continue());
    await panel.getByRole('button', { name: copy.MediaRoots.addDirectory, exact: true }).click();
    await selectOtherRoot(page, copy, roots[1]);
    await expect(panel.getByRole('alert')).toHaveText(copy.MediaRoots.saveFailed);
    await expect(page.locator('#media-root-1')).toHaveValue(roots[1]);
    await expect(panel.getByRole('button', { name: copy.MediaRoots.retry, exact: true })).toBeEnabled();
    expect((await read(request, `${backend}/settings/media-dirs`)).media_dirs).toEqual([roots[0]]);
    reject = false;
    await panel.getByRole('button', { name: copy.MediaRoots.retry, exact: true }).click();
    await expect(panel.getByRole('status')).toHaveText(copy.MediaRoots.saved);
    expect((await read(request, `${backend}/settings/media-dirs`)).media_dirs).toEqual(roots);
    await page.reload();
    await expect(page.locator('#media-root-1')).toHaveValue(roots[1]);
    await expect(panel.getByRole('img', { name: copy.MediaRoots.accessible, exact: true })).toHaveCount(2);
    await expect(panel.getByRole('button', { name: copy.MediaRoots.makePrimary, exact: true })).toHaveCount(0);
    await panel.getByRole('button', { name: copy.MediaRoots.removeDirectory.replace('{number}', '1'), exact: true }).click();
    await expect.poll(async () => (await read(request, `${backend}/settings/media-dirs`)).media_dirs).toEqual([roots[1]]);
    await panel.getByRole('button', { name: copy.MediaRoots.addDirectory, exact: true }).click();
    await selectOtherRoot(page, copy, roots[0]);
    await expect(page.locator('#media-root-0')).toHaveValue(roots[1]);
    await expect.poll(async () => (await read(request, `${backend}/settings/media-dirs`)).media_dirs).toEqual([...roots].reverse());
    const remove = panel.getByRole('button', { name: copy.MediaRoots.removeDirectory.replace('{number}', '2'), exact: true });
    await remove.focus(); await page.keyboard.press('Space');
    await expect.poll(async () => (await read(request, `${backend}/settings/media-dirs`)).media_dirs).toEqual([roots[1]]);
    await page.reload(); await expect(page.locator('#media-root-0')).toHaveValue(roots[1]);
    await expect(page.locator('#media-root-1')).toHaveCount(0);
  });

  test(`${locale} health autosave rejects failure and preserves hidden schedule on success`, async ({ page, request }) => {
    let reject = true;
    const writes: object[] = [];
    await page.route('**/api/maintenance/video-health/config', route => {
      if (route.request().method() !== 'PUT') return route.continue();
      writes.push(route.request().postDataJSON());
      return reject ? route.fulfill({ status: 503, json: { detail: 'E2E unavailable' } }) : route.continue();
    });
    await page.goto(`/${locale}/settings?section=library`);
    const video = page.locator('section[aria-labelledby="video-health-settings"]');
    const toggle = video.getByRole('switch', { name: copy.VideoHealth.automatic, exact: true });
    await expect(toggle).toHaveAttribute('aria-checked', 'true');
    await toggle.focus(); await page.keyboard.press('Space');
    await expect(video.getByRole('alert')).toHaveText(copy.VideoHealth.writeFailed);
    await expect(toggle).toHaveAttribute('aria-checked', 'true');
    await expect(toggle).toBeEnabled();
    await expect(video.getByRole('status')).toHaveCount(0);
    expect((await read(request, health)).config).toMatchObject(schedule);
    await video.screenshot({ path: `e2e-artifacts/settings-health-failed-${locale}.png` });
    reject = false;
    await toggle.focus(); await page.keyboard.press('Space');
    await expect(toggle).toHaveAttribute('aria-checked', 'false');
    await expect(video.getByRole('status')).toHaveText(copy.VideoHealth.accepted);
    expect((await read(request, health)).config).toMatchObject({ ...schedule, enabled: false });
    expect(writes).toEqual([{ enabled: false }, { enabled: false }]);
    await page.reload();
    await expect(toggle).toHaveAttribute('aria-checked', 'false');
  });

  test(`${locale} every directory status remains available by keyboard and errors stay visible`, async ({ page }) => {
    const states = ['accessible', 'offline', 'permission_denied', 'unavailable'] as const;
    await page.route('**/api/settings/media-dirs', route => route.fulfill({ json: {
      media_dirs: states.map((_, index) => `${roots[0]}-${index}`),
      roots: states.map((state, index) => ({ id: String(index), path: `${roots[0]}-${index}`, state })),
    } }));
    await page.goto(`/${locale}/settings?section=library`);
    const panel = page.getByLabel(copy.MediaRoots.title, { exact: true });
    for (const state of states) {
      const icon = panel.getByRole('img', { name: copy.MediaRoots[state], exact: true });
      await icon.focus();
      await expect(page.locator(`#${await icon.getAttribute('aria-describedby')}`)).toBeVisible();
    }
    await page.screenshot({ path: `e2e-artifacts/settings-root-states-${locale}.png`, fullPage: true });
    await page.unroute('**/api/settings/media-dirs');
    await page.route('**/api/settings/media-dirs', route => route.fulfill({ status: 503, json: {} }));
    await page.route('**/api/maintenance/video-health', route => route.fulfill({ status: 503, json: {} }));
    await page.reload();
    await expect(panel.getByRole('alert')).toHaveText(copy.MediaRoots.loadFailed);
    await expect(page.locator('section[aria-labelledby="video-health-settings"]').getByRole('alert')).toHaveText(copy.VideoHealth.loadFailed);
    await page.screenshot({ path: `e2e-artifacts/settings-load-failed-${locale}.png`, fullPage: true });
  });
}
