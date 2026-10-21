import { test, expect, type Page } from '@playwright/test';
import { writeFile } from 'node:fs/promises';
import path from 'node:path';
import en from '../messages/en.json';
import zh from '../messages/zh.json';
import { expectAnnouncedOnly } from './settings-feedback-assertions';

const backend = process.env.E2E_BACKEND!;
const gate = () => { let release!: () => void; const promise = new Promise<void>(resolve => { release = resolve; }); return { promise, release }; };
let roots: string[];
async function capture(page: Page, filename: string) {
  await page.evaluate(async () => { await document.fonts.ready; window.scrollTo(0, 0); });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: path.join('e2e-artifacts', filename), fullPage: true, animations: 'disabled' });
}
test.beforeAll(async ({ request }) => {
  const response = await request.post(`${backend}/__e2e/control`, { headers: { 'x-e2e-token': process.env.E2E_TOKEN! }, data: { action: 'multi_root_fixture' } });
  expect(response.ok()).toBeTruthy(); roots = (await response.json()).roots;
});
test.beforeEach(async ({ context }) => {
  await context.route('**/*', route => ['127.0.0.1', 'localhost'].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort('blockedbyclient'));
});
for (const locale of ['en', 'zh'] as const) {
  const copy = locale === 'en' ? en : zh;
  for (const width of [1440, 390, 320]) test(`${locale} input bodies align through load, test, save, validation and retry at ${width}px`, async ({ page }) => {
    const reads = gate(), tests = gate(), urlWrite = gate(), keyWrite = gate(), modelWrite = gate();
    let url = 'https://synthetic.invalid/v1', model = 'synthetic-model-a', configured = true;
    let testFail = false, urlFail = false, keyFail = true, modelFail = false;
    let apiTests = 0, tmdbTests = 0; const urlWrites: string[] = [], keyWrites: string[] = [];
    const longModel = 'synthetic-model-b-with-an-intentionally-long-name';
    await page.route('**/api/settings/model*', async route => {
      if (route.request().method() === 'GET') await reads.promise;
      else { await modelWrite.promise; if (modelFail) return route.fulfill({ status: 503, json: {} }); model = new URL(route.request().url()).searchParams.get('model_name')!; }
      return route.fulfill({ json: { current_model: model, available_models: ['synthetic-model-a', longModel] } });
    });
    await page.route('**/api/settings/base-url*', async route => {
      if (route.request().method() === 'GET') await reads.promise;
      else {
        urlWrites.push(new URL(route.request().url()).searchParams.get('base_url')!); await urlWrite.promise;
        if (urlFail) return route.fulfill({ status: 503, json: {} });
        url = urlWrites.at(-1)!;
      }
      return route.fulfill({ json: { base_url: url } });
    });
    await page.route('**/api/settings/tmdb', async route => {
      if (route.request().method() === 'GET') await reads.promise;
      else {
        keyWrites.push(route.request().postDataJSON().api_key); await keyWrite.promise;
        if (keyFail) return route.fulfill({ status: 503, json: {} });
        configured = Boolean(keyWrites.at(-1));
      }
      return route.fulfill({ json: { status: 'success', configured, source: configured ? 'settings' : null } });
    });
    await page.route('**/api/settings/test-api-key', async route => {
      apiTests += 1; await tests.promise;
      return route.fulfill({ status: testFail ? 503 : 200, json: { status: 'success', message: 'Synthetic provider response must not render' } });
    });
    await page.route('**/api/settings/tmdb/test', async route => {
      tmdbTests += 1; await tests.promise;
      return route.fulfill({ json: { status: testFail ? 'error' : 'success', message: 'Synthetic provider response must not render' } });
    });
    const measurements: object[] = [];
    try {
      await page.setViewportSize({ width, height: 1000 }); await page.goto(`/${locale}/settings?section=connections`);
      const group = page.getByRole('group', { name: copy.Settings.model, exact: true });
      const select = group.locator('button[aria-expanded]'), urlInput = page.getByRole('textbox', { name: copy.Settings.baseUrl, exact: true });
      const keyInput = page.getByLabel(copy.Settings.tmdbApiKey, { exact: true });
      const api = page.getByRole('button', { name: copy.Settings.testConnection, exact: true }), tmdb = page.getByRole('button', { name: copy.Settings.tmdbTestBtn, exact: true });
      await expect(urlInput).toBeVisible(); await expect(keyInput).toBeDisabled();
      const baseline = (await select.boundingBox())!;
      const measure = async (phase: string) => {
        const boxes = await Promise.all([select, urlInput, keyInput].map(input => input.boundingBox()));
        for (const box of boxes) {
          expect(box).not.toBeNull();
          expect(Math.abs(box!.x - baseline.x)).toBeLessThanOrEqual(0.5);
          expect(Math.abs(box!.width - baseline.width)).toBeLessThanOrEqual(0.5);
          expect(Math.abs(box!.x + box!.width - baseline.x - baseline.width)).toBeLessThanOrEqual(0.5);
        }
        for (const button of [api, tmdb]) {
          const box = (await button.boundingBox())!; expect(box.x).toBeGreaterThanOrEqual(baseline.x + baseline.width + 7);
        }
        measurements.push({ phase, inputs: boxes });
      };
      const savedOnly = async () => {
        const messages = page.getByText(copy.Settings.saved, { exact: true });
        await expect.poll(() => messages.count()).toBeGreaterThan(0);
        for (const status of await messages.all()) await expectAnnouncedOnly(status, copy.Settings.saved);
      };
      await measure('loading'); await capture(page, `alignment-${locale}-${width}-loading.png`);
      reads.release(); await expect(api).toBeEnabled(); await expect(keyInput).toBeEnabled(); await measure('loaded');
      await expect(page.getByText(copy.Settings.tmdbApiKeyDesc, { exact: true })).toHaveCount(0);
      await api.click(); await tmdb.click(); await expect(api).toHaveAttribute('aria-busy', 'true'); await expect(tmdb).toHaveAttribute('aria-busy', 'true');
      await measure('tests-pending'); tests.release();
      await expect(page.getByRole('img', { name: copy.Settings.connectionTestPassed, exact: true })).toHaveCount(2);
      await measure('test-success'); await capture(page, `alignment-${locale}-${width}-test-success.png`);
      testFail = true; await api.click(); await tmdb.click();
      await expect(page.getByRole('img', { name: copy.Settings.connectionTestFailed, exact: true })).toHaveCount(2); await measure('test-error');
      await urlInput.fill('https://'); await urlInput.press('Enter');
      await expect(page.getByText(copy.Settings.invalidBaseUrl, { exact: true })).toBeVisible(); await measure('validation-error'); expect(urlWrites).toEqual([]);
      await urlInput.fill('https://saved.invalid/v1'); await urlInput.press('Enter'); await expect.poll(() => urlWrites.length).toBe(1);
      await measure('url-saving'); urlWrite.release(); await savedOnly(); await measure('url-saved');
      urlFail = true; await urlInput.fill('https://retry.invalid/v1'); await urlInput.press('Enter');
      await expect(page.getByText(copy.Settings.baseUrlSaveFailed, { exact: true })).toBeVisible(); await measure('url-save-error');
      await capture(page, `alignment-${locale}-${width}-save-error.png`);
      urlFail = false; await page.getByRole('button', { name: copy.Settings.retrySave, exact: true }).click(); await savedOnly(); await measure('url-retried');
      expect(url).toBe('https://retry.invalid/v1');
      await keyInput.fill('synthetic-key'); expect(keyWrites).toEqual([]); await keyInput.press('Enter'); await expect.poll(() => keyWrites.length).toBe(1);
      await expect(keyInput).toHaveAttribute('aria-busy', 'true'); await measure('tmdb-saving');
      await capture(page, `alignment-${locale}-${width}-tmdb-saving.png`); keyWrite.release();
      await expect(page.getByText(copy.Settings.tmdbSaveFailed, { exact: true })).toBeVisible(); await expect(keyInput).toHaveValue('synthetic-key'); await measure('tmdb-save-error');
      keyFail = false; await page.getByRole('button', { name: copy.Settings.retrySave, exact: true }).click();
      await expect(keyInput).toHaveValue(''); await savedOnly(); await measure('tmdb-saved');
      await select.click(); await page.getByRole('button', { name: longModel, exact: true }).click();
      await expect(select).toBeDisabled(); await measure('model-saving'); modelWrite.release();
      await expect(select).toBeEnabled(); await expect(select).toContainText(longModel); await savedOnly(); await measure('model-saved');
      await capture(page, `alignment-${locale}-${width}-saved.png`);
      modelFail = true; await select.click(); await page.getByRole('button', { name: 'synthetic-model-a', exact: true }).click();
      await expect(page.getByText(copy.Settings.modelSaveFailed, { exact: true })).toBeVisible(); await measure('model-save-error');
      await expect(group.locator('..').locator('..').getByText(copy.Settings.saved, { exact: true })).toHaveCount(0);
      expect(apiTests).toBe(2); expect(tmdbTests).toBe(2);
      await expect(page.getByText('Synthetic provider response must not render', { exact: true })).toHaveCount(0);
      await writeFile(path.join('e2e-artifacts', `alignment-${locale}-${width}-bounds.json`), JSON.stringify(measurements, null, 2));
    } finally { reads.release(); tests.release(); urlWrite.release(); keyWrite.release(); modelWrite.release(); }
  });

  test(`${locale} directory and Library preference successes remain screen-reader-only`, async ({ page }) => {
    let directories = [roots[0]], watch = false, organize = false, confirmation = false, artwork = 'metadata', video = false;
    const result = () => ({ media_dirs: directories, roots: directories.map((folder, index) => ({ id: String(index), path: folder, state: 'accessible' })) });
    await page.route('**/api/settings/media-dirs', route => {
      if (route.request().method() === 'PUT') directories = route.request().postDataJSON().media_dirs;
      return route.fulfill({ json: result() });
    });
    for (const kind of ['library-watch', 'auto-organize-root', 'scrape-confirmation', 'artwork-language']) await page.route(`**/api/settings/${kind}*`, route => {
      const query = new URL(route.request().url()).searchParams;
      if (route.request().method() === 'PUT') {
        if (kind === 'library-watch') watch = query.get('enabled') === 'true';
        if (kind === 'auto-organize-root') organize = query.get('enabled') === 'true';
        if (kind === 'scrape-confirmation') confirmation = query.get('enabled') === 'true';
        if (kind === 'artwork-language') artwork = query.get('language')!;
      }
      const data = kind === 'library-watch' ? { watch_library: watch, watcher: { running: watch, media_dir: roots[0], last_event_at: null, last_error: null, pending: 0 } }
        : kind === 'auto-organize-root' ? { auto_organize_root_videos: organize } : kind === 'scrape-confirmation' ? { scrape_require_confirmation: confirmation } : { artwork_language: artwork };
      return route.fulfill({ json: data });
    });
    await page.route('**/api/maintenance/video-health/config', route => { video = route.request().postDataJSON().enabled; return route.fulfill({ json: {} }); });
    await page.route('**/api/maintenance/video-health', route => route.fulfill({ json: { config: { enabled: video, paused: true, start_minute: 0, end_minute: 1440, daily_budget_minutes: 7 }, counts: {}, total: 0, unread: 0, load: { observable: false } } }));
    await page.setViewportSize({ width: 320, height: 1000 }); await page.goto(`/${locale}/settings?section=library`);
    const rootsPanel = page.getByLabel(copy.MediaRoots.title, { exact: true });
    await expect(page.locator('#media-root-0')).toHaveValue(roots[0]);
    await rootsPanel.getByRole('button', { name: copy.MediaRoots.addDirectory, exact: true }).click();
    const picker = page.getByRole('dialog', { name: copy.FileBrowser.title, exact: true });
    await picker.getByRole('button', { name: copy.FileBrowser.up }).click(); await picker.getByText(path.basename(roots[1]), { exact: true }).click();
    await expect(picker.getByText(roots[1], { exact: true })).toBeVisible(); await picker.getByRole('button', { name: copy.FileBrowser.selectCurrent, exact: true }).click();
    await expectAnnouncedOnly(rootsPanel.getByRole('status'), copy.MediaRoots.saved); expect(directories).toEqual(roots);
    for (const label of [copy.Settings.autoScan, copy.Settings.autoOrganizeRoot, copy.Settings.scrapeRequireConfirmation]) {
      const control = page.getByRole('switch', { name: label, exact: true }); await control.click(); await expect(control).toHaveAttribute('aria-checked', 'true');
      const row = control.locator('..').locator('..').locator('..'); await expectAnnouncedOnly(row.getByText(copy.Settings.saved, { exact: true }), copy.Settings.saved);
    }
    await page.getByRole('button', { name: copy.Settings.artworkLanguageEn, exact: true }).click();
    await expect.poll(() => artwork).toBe('en');
    for (const status of await page.getByText(copy.Settings.saved, { exact: true }).all()) await expectAnnouncedOnly(status, copy.Settings.saved);
    const videoPanel = page.locator('section[aria-labelledby="video-health-settings"]'); await videoPanel.getByRole('switch').click();
    await expect(videoPanel.getByRole('switch')).toHaveAttribute('aria-checked', 'true'); await expectAnnouncedOnly(videoPanel.getByRole('status'), copy.VideoHealth.accepted);
    await expect(page.getByText(copy.Settings.watching, { exact: true })).toHaveCount(0);
    await expect(page.getByText(copy.VideoHealth.automaticDescription, { exact: true })).toBeVisible();
    await expect(page.getByText(copy.Settings.scrapeRequireConfirmationDesc, { exact: true })).toBeVisible();
    await capture(page, `alignment-${locale}-320-library-saved.png`);
  });
}
