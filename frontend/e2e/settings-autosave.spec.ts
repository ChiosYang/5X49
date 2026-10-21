import { test, expect, type APIRequestContext, type Page } from '@playwright/test';
import path from 'node:path';
import en from '../messages/en.json';
import zh from '../messages/zh.json';
import type { WorkflowRunView } from '../src/types/movie';

const backend = process.env.E2E_BACKEND!;
const copies = { en, zh };
let roots: string[], originalRoots: string[], originalUrl: string, originalLanguage: string;
const gate = () => { let release!: () => void; const promise = new Promise<void>(resolve => { release = resolve; }); return { promise, release }; };
async function read(request: APIRequestContext, endpoint: string) { const response = await request.get(`${backend}${endpoint}`); expect(response.ok()).toBeTruthy(); return response.json(); }
async function put(request: APIRequestContext, endpoint: string, data?: object) { expect((await request.put(`${backend}${endpoint}`, { data })).ok()).toBeTruthy(); }
async function choose(page: Page, locale: 'en' | 'zh', width: number, section: keyof typeof en.SettingsArea) {
  const copy = copies[locale];
  if (width < 768) {
    await page.getByRole('button', { name: copy.SettingsArea.categories, exact: true }).click();
    await page.getByRole('dialog', { name: copy.Settings.settingsNavigation, exact: true }).getByRole('link', { name: copy.SettingsArea[section], exact: true }).click();
    await expect(page.getByRole('dialog')).toHaveCount(0);
  } else await page.getByRole('navigation', { name: copy.Settings.settingsNavigation, exact: true }).getByRole('link', { name: copy.SettingsArea[section], exact: true }).click();
  await expect(page.locator(`#settings-title-${section}`)).toBeVisible();
}

for (const kind of ['roots', 'url'] as const) test(`${kind} pending save and queued completion survive leaving and remounting Settings`, async ({ page, request }) => {
  const held = gate(), newerCommitted = gate(); const payloads: unknown[] = []; let active = 0, maximum = 0;
  const values = kind === 'roots' ? [roots[1], path.join(process.env.E2E_ROOT!, 'normal/media'), roots[0]]
    : ['https://old.invalid/v1', 'https://queued.invalid/v1', 'https://newest.invalid/v1'];
  const endpoint = kind === 'roots' ? '/settings/media-dirs' : '/settings/base-url';
  await page.route(kind === 'roots' ? '**/api/settings/media-dirs' : /\/api\/settings\/base-url\?/, async route => {
    if (route.request().method() !== 'PUT') return route.continue();
    const value = kind === 'roots' ? route.request().postDataJSON().media_dirs[0] : new URL(route.request().url()).searchParams.get('base_url');
    payloads.push(value); active += 1; maximum = Math.max(maximum, active);
    if (payloads.length === 1) await held.promise;
    try { await route.fulfill({ response: await route.fetch() }); if (value === values[2]) newerCommitted.release(); }
    finally { active -= 1; }
  });
  try {
    await page.setViewportSize({ width: 320, height: 1000 });
    await page.goto(`/en/settings?section=${kind === 'roots' ? 'library' : 'connections'}`);
    const input = kind === 'roots' ? page.locator('#media-root-0') : page.getByRole('textbox', { name: en.Settings.baseUrl, exact: true });
    await expect(input).toHaveValue(kind === 'roots' ? roots[0] : originalUrl);
    await input.fill(values[0]); await input.press('Enter'); await expect.poll(() => payloads.length).toBe(1);
    await input.fill(values[1]); await input.press('Enter');
    await choose(page, 'en', 320, 'library-maintenance');
    await page.getByRole('link', { name: en.LibraryManagement.constellation.actions['review-metadata'].label, exact: true }).click();
    await expect(page).toHaveURL(/\/library\?.*view=metadata/); await expect(page.locator('#settings-title-library-maintenance')).toHaveCount(0);
    await page.goBack(); await expect(page.locator('#settings-title-library-maintenance')).toBeVisible();
    await choose(page, 'en', 320, kind === 'roots' ? 'library' : 'connections');
    await expect(input).toBeVisible(); await input.fill(values[2]); await input.press('Enter');
    // Give a wrongly independent remount writer a bounded chance to commit B before A.
    await Promise.race([newerCommitted.promise, new Promise(resolve => setTimeout(resolve, 300))]);
    held.release();
    await expect.poll(() => payloads.length).toBeGreaterThanOrEqual(2);
    expect(maximum).toBe(1); expect(payloads).toEqual([values[0], values[2]]);
    await expect.poll(async () => { const result = await read(request, endpoint); return kind === 'roots' ? result.media_dirs[0] : result.base_url; }).toBe(values[2]);
    await expect(input).toHaveValue(values[2]); await page.reload(); await expect(input).toHaveValue(values[2]);
  } finally { held.release(); }
});
async function capture(page: Page, filename: string) {
  await page.evaluate(async () => { await document.fonts.ready; window.scrollTo(0, 0); });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: path.join('e2e-artifacts', filename), fullPage: true, animations: 'disabled' });
}
test.beforeAll(async ({ request }) => {
  originalRoots = (await read(request, '/settings/media-dirs')).media_dirs;
  originalUrl = (await read(request, '/settings/base-url')).base_url;
  originalLanguage = (await read(request, '/settings/language')).language;
  const fixture = await request.post(`${backend}/__e2e/control`, { headers: { 'x-e2e-token': process.env.E2E_TOKEN! }, data: { action: 'multi_root_fixture' } });
  expect(fixture.ok()).toBeTruthy(); roots = (await fixture.json()).roots;
});
test.beforeEach(async ({ context, request }) => {
  await put(request, '/settings/media-dirs', { media_dirs: [roots[0]] });
  await put(request, `/settings/base-url?base_url=${encodeURIComponent(originalUrl)}`);
  await context.route('**/*', route => ['127.0.0.1', 'localhost'].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort('blockedbyclient'));
});
test.afterAll(async ({ request }) => {
  await put(request, '/settings/media-dirs', { media_dirs: originalRoots });
  await put(request, `/settings/base-url?base_url=${encodeURIComponent(originalUrl)}`);
  await put(request, `/settings/language?language=${originalLanguage}`);
});

for (const locale of ['en', 'zh'] as const) {
  const copy = copies[locale];
  for (const width of [1440, 390, 320]) test(`${locale} compact controls and icon actions at ${width}px`, async ({ page, request }) => {
    await put(request, `/settings/language?language=${locale === 'en' ? 'zh' : 'en'}`);
    const writes: string[] = [];
    page.on('request', request => { if (request.method() !== 'GET' && request.url().includes('/api/')) writes.push(new URL(request.url()).pathname); });
    await page.setViewportSize({ width, height: 1000 }); await page.goto(`/${locale}/settings?section=general`);
    const language = page.getByRole('group', { name: copy.Settings.languagePref, exact: true });
    await language.getByRole('button', { name: locale, exact: true }).focus(); await page.keyboard.press('Enter');
    await expect(language.getByRole('button', { name: locale, exact: true })).toHaveAttribute('aria-pressed', 'true');
    const languageHeight = (await language.boundingBox())!.height;
    await capture(page, `autosave-${locale}-${width}-general.png`);
    await choose(page, locale, width, 'library');
    const toggle = page.getByRole('switch', { name: copy.Settings.autoScan, exact: true });
    expect(languageHeight).toBe((await toggle.boundingBox())!.height);
    await expect(page.getByText(copy.Settings.notWatching, { exact: true })).toHaveCount(0);
    await expect(page.getByText(copy.VideoHealth.automaticDescription, { exact: true })).toBeVisible();
    const panel = page.getByLabel(copy.MediaRoots.title, { exact: true });
    const add = panel.getByRole('button', { name: copy.MediaRoots.addDirectory, exact: true });
    await expect(add).toBeEnabled(); expect(await add.textContent()).toBe('');
    const header = await panel.getByRole('heading', { name: copy.MediaRoots.title, exact: true }).boundingBox();
    const icon = await add.boundingBox(); expect(header && icon && icon.x >= header.x + header.width).toBeTruthy();
    await add.focus(); await expect(page.locator('#add-directory-tooltip')).toBeVisible(); await page.keyboard.press('Space');
    await expect(page.locator('#media-root-1')).toBeFocused(); await expect(page.locator('#media-root-1')).toHaveValue('');
    await page.locator('#media-root-1').fill('C:'); await page.locator('#media-root-1').press('Enter');
    await expect(panel.getByRole('alert')).toHaveText(copy.MediaRoots.absolute);
    await panel.getByRole('button', { name: copy.MediaRoots.discard, exact: true }).click();
    await expect(panel.getByRole('button', { name: copy.MediaRoots.add, exact: true })).toHaveCount(0);
    await expect(panel.getByRole('button', { name: copy.MediaRoots.save, exact: true })).toHaveCount(0);
    await capture(page, `autosave-${locale}-${width}-library.png`);
    await choose(page, locale, width, 'connections');
    const model = page.getByRole('group', { name: copy.Settings.model, exact: true });
    const testConnection = model.getByRole('button', { name: copy.Settings.testConnection, exact: true });
    const dropdown = model.locator('button[aria-expanded]');
    const modelBounds = await dropdown.boundingBox(), testBounds = await testConnection.boundingBox();
    expect(modelBounds && testBounds && testBounds.x >= modelBounds.x + modelBounds.width).toBeTruthy();
    expect(await testConnection.textContent()).toBe(''); await testConnection.focus();
    await expect(page.locator('#api-test-tooltip')).toBeVisible();
    await expect(page.getByText(copy.Settings.apiKey, { exact: true })).toHaveCount(0);
    await expect(page.getByText(copy.Settings.testBtn, { exact: true })).toHaveCount(0);
    const urlRow = page.getByRole('textbox', { name: copy.Settings.baseUrl, exact: true }).locator('..').locator('..');
    await expect(urlRow.getByRole('button', { name: copy.Settings.save, exact: true })).toHaveCount(0);
    for (const preset of ['OpenRouter', 'OpenAI', 'Anthropic']) await expect(page.getByRole('button', { name: preset, exact: true })).toHaveCount(0);
    await capture(page, `autosave-${locale}-${width}-connections.png`);
    expect(writes).toEqual(['/api/settings/language']);
  });

  test(`${locale} directory autosave serializes fast edits and guards every scan until latest save`, async ({ page, request }) => {
    // Own only this runner's synthetic database; make the first-scan form deterministic.
    const empty = await request.post(`${backend}/__e2e/control`, { headers: { 'x-e2e-token': process.env.E2E_TOKEN! }, data: { action: 'identity_cleanup' } });
    expect(empty.ok()).toBeTruthy();
    const first = gate(), second = gate(); const payloads: string[][] = []; let active = 0, maximum = 0;
    const forbidden: string[] = [];
    page.on('request', request => {
      if ((request.method() === 'POST' && /\/api\/(library\/scan|workflows\/.*\/retry)/.test(request.url()))
        || (request.method() === 'PUT' && /\/api\/settings\/media-dir(?:\?|$)/.test(request.url()))) forbidden.push(request.url());
    });
    await page.route('**/api/settings/media-dirs', async route => {
      if (route.request().method() !== 'PUT') return route.continue();
      payloads.push(route.request().postDataJSON().media_dirs); active += 1; maximum = Math.max(maximum, active);
      if (payloads.length === 1) await first.promise; else if (payloads.length === 2) await second.promise;
      try { await route.fulfill({ response: await route.fetch() }); } finally { active -= 1; }
    });
    const records: WorkflowRunView[] = ['library.reconcile', 'library.scan_folder', 'library.refresh_item'].map((type, index) => ({
      id: `guard_scan_${index}`, type, status: 'failed', definition_version: `${type}.v1`, subject_type: 'library', steps: [], created_at: '2026-10-20', updated_at: '2026-10-20',
    }));
    await page.route(/\/api\/workflows(?:\?|$)/, route => route.fulfill({ json: records }));
    await page.route('**/api/library/missing', route => route.fulfill({ json: { count: 1, items: [{ library_item_id: 'test_item', film_id: 'test_film', title: 'Synthetic offline edition' }] } }));
    const guards = async (disabled: boolean) => {
      for (const name of [copy.MediaRoots.scanAll, copy.LibraryCare.scanAgain]) {
        const button = page.getByRole('button', { name, exact: true });
        if (disabled) await expect(button).toBeDisabled(); else await expect(button).toBeEnabled();
      }
      const retry = page.getByRole('region', { name: copy.SettingsArea.recentWorkflows, exact: true }).getByRole('button', { name: copy.LibraryManagement.constellation.retryWorkflow, exact: true });
      await expect(retry).toHaveCount(3); for (const button of await retry.all()) { if (disabled) await expect(button).toBeDisabled(); else await expect(button).toBeEnabled(); }
      await page.getByRole('button', { name: copy.WorkflowStatus.label, exact: true }).click();
      const globalRetries = page.locator('#workflow-status-panel').getByRole('button', { name: copy.WorkflowStatus.retry, exact: true });
      await expect(globalRetries).toHaveCount(3);
      for (const button of await globalRetries.all()) await expect(button).toHaveAttribute('aria-disabled', String(disabled));
      if (disabled) await globalRetries.first().click({ force: true });
      await page.keyboard.press('Escape'); await expect(page.locator('#workflow-status-panel')).toBeHidden();
    };
    try {
      await page.setViewportSize({ width: 320, height: 1000 }); await page.goto(`/${locale}/settings?section=library`);
      const input = page.locator('#media-root-0'); await expect(input).toHaveValue(roots[0]); await input.fill(roots[1]);
      expect(payloads).toEqual([]); await input.press('Enter'); await expect.poll(() => payloads.length).toBe(1);
      await choose(page, locale, 320, 'library-maintenance'); await guards(true);
      await choose(page, locale, 320, 'library');
      const other = path.join(process.env.E2E_ROOT!, 'normal/media'); await input.fill(other); await input.press('Enter');
      await input.fill('unfinished'); await choose(page, locale, 320, 'library-maintenance'); await guards(true);
      first.release(); await expect.poll(async () => (await read(request, '/settings/media-dirs')).media_dirs).toEqual([roots[1]]);
      await choose(page, locale, 320, 'library'); await expect(input).toHaveValue('unfinished');
      await expect(page.getByLabel(copy.MediaRoots.title, { exact: true }).getByRole('status')).toHaveCount(0); expect(payloads).toEqual([[roots[1]]]);
      await input.fill(other); await input.press('Enter'); await expect.poll(() => payloads.length).toBe(2);
      await input.fill(roots[0]); await input.press('Enter'); await choose(page, locale, 320, 'library-maintenance'); await guards(true);
      await capture(page, `autosave-${locale}-320-pending-scan-guards.png`);
      await page.getByRole('link', { name: copy.LibraryManagement.constellation.actions['review-metadata'].label, exact: true }).click();
      await expect(page).toHaveURL(/\/library\?.*view=metadata/);
      await expect(page.locator('#settings-title-library-maintenance')).toHaveCount(0);
      await expect(page.getByRole('button', { name: copy.LibraryCare.scanNow, exact: true })).toBeDisabled();
      await page.getByRole('button', { name: copy.WorkflowStatus.label, exact: true }).click();
      const awayRetries = page.locator('#workflow-status-panel').getByRole('button', { name: copy.WorkflowStatus.retry, exact: true });
      await expect(awayRetries).toHaveCount(3);
      for (const button of await awayRetries.all()) await expect(button).toHaveAttribute('aria-disabled', 'true');
      await page.keyboard.press('Escape');
      await page.getByRole('navigation', { name: copy.LibraryCare.careNavigation, exact: true }).getByRole('link', { name: copy.LibraryCare.allFilms, exact: true }).click();
      await expect(page.getByRole('button', { name: copy.Onboarding.scanNow, exact: true })).toBeDisabled();
      second.release(); await expect.poll(() => payloads.length).toBe(3);
      await expect.poll(async () => (await read(request, '/settings/media-dirs')).media_dirs).toEqual([roots[0]]);
      await page.goBack(); await expect(page).toHaveURL(/\/library\?.*view=metadata/);
      await page.goBack(); await expect(page.locator('#settings-title-library-maintenance')).toBeVisible();
      await guards(false); expect(maximum).toBe(1); expect(forbidden).toEqual([]);
      expect(payloads).toEqual([[roots[1]], [other], [roots[0]]]);
      await page.reload(); await choose(page, locale, 320, 'library'); await expect(input).toHaveValue(roots[0]);
    } finally { first.release(); second.release(); }
  });

  test(`${locale} URL completion retains newer drafts and never changes models or calls providers`, async ({ page, request }) => {
    const held = gate(); let fail = true, count = 0; const urls: string[] = [], providerCalls: string[] = [], modelReads: string[] = [], otherWrites: string[] = [];
    const originalModel = (await read(request, '/settings/model')).current_model;
    page.on('request', request => {
      const url = new URL(request.url());
      if (/\/api\/settings\/(test-api-key|models\/refresh)/.test(url.pathname)) providerCalls.push(url.pathname);
      if (url.pathname === '/api/settings/model') modelReads.push(request.method());
      if (request.method() !== 'GET' && url.pathname.startsWith('/api/settings/') && url.pathname !== '/api/settings/base-url') otherWrites.push(url.pathname);
    });
    await page.route(/\/api\/settings\/base-url\?/, async route => {
      if (route.request().method() !== 'PUT') return route.continue();
      const url = new URL(route.request().url()); expect([...url.searchParams.keys()]).toEqual(['base_url']); expect(route.request().postData()).toBeNull();
      urls.push(url.searchParams.get('base_url')!); count += 1;
      if (count === 1) await held.promise;
      if (fail) return route.fulfill({ status: 503, json: {} });
      return route.fulfill({ response: await route.fetch() });
    });
    try {
      await page.setViewportSize({ width: 320, height: 1000 }); await page.goto(`/${locale}/settings?section=connections`);
      const input = page.getByRole('textbox', { name: copy.Settings.baseUrl, exact: true }); await expect(input).toHaveValue(originalUrl);
      const keyDraft = page.getByLabel(copy.Settings.tmdbApiKey, { exact: true });
      await keyDraft.fill('synthetic-unsent-draft');
      await input.fill('https://'); await input.press('Enter'); await expect(page.getByText(copy.Settings.invalidBaseUrl, { exact: true })).toBeVisible(); expect(urls).toEqual([]);
      await input.fill('https://first.invalid/v1'); await input.press('Enter'); await expect.poll(() => count).toBe(1);
      await input.fill('https://latest.invalid/v1');
      await choose(page, locale, 320, 'general'); await page.goBack(); await expect(input).toHaveValue('https://latest.invalid/v1');
      const group = page.getByRole('group', { name: copy.Settings.model, exact: true });
      await group.locator('button[aria-expanded]').click(); await page.getByRole('searchbox', { name: copy.Settings.searchModels, exact: true }).fill('kept-model-search');
      const readsBefore = modelReads.length; held.release();
      await expect(page.getByText(copy.Settings.baseUrlSaveFailed, { exact: true })).toBeVisible();
      await expect(page.getByRole('searchbox', { name: copy.Settings.searchModels, exact: true })).toHaveValue('kept-model-search');
      await page.getByRole('button', { name: copy.Settings.closeModelMenu, exact: true }).focus();
      await page.keyboard.press('Enter');
      await expect(input).toHaveValue('https://latest.invalid/v1'); expect(urls).toEqual(['https://first.invalid/v1']);
      await capture(page, `autosave-${locale}-320-url-retry.png`);
      fail = false; await page.getByRole('button', { name: copy.Settings.retrySave, exact: true }).click();
      await expect(page.getByText(copy.Settings.saved, { exact: true })).toBeVisible();
      expect(urls).toEqual(['https://first.invalid/v1', 'https://latest.invalid/v1']); expect(modelReads.length).toBe(readsBefore); expect(providerCalls).toEqual([]);
      expect((await read(request, '/settings/model')).current_model).toBe(originalModel);
      expect((await read(request, '/settings/base-url')).base_url).toBe('https://latest.invalid/v1');
      await expect(keyDraft).toHaveValue('synthetic-unsent-draft');
      await input.fill('https://blur.invalid/v1'); await input.press('Tab');
      await expect.poll(async () => (await read(request, '/settings/base-url')).base_url).toBe('https://blur.invalid/v1');
      expect(urls).toEqual(['https://first.invalid/v1', 'https://latest.invalid/v1', 'https://blur.invalid/v1']);
      await expect(keyDraft).toHaveValue('synthetic-unsent-draft'); expect(otherWrites).toEqual([]); expect(providerCalls).toEqual([]);
      await page.reload(); await expect(input).toHaveValue('https://blur.invalid/v1');
    } finally { held.release(); }
  });

  test(`${locale} model-side connection icon preserves keyboard, loading, failure and retry with mocks`, async ({ page }) => {
    const held = gate(); let calls = 0;
    await page.route('**/api/settings/test-api-key', async route => {
      calls += 1; if (calls === 1) { await held.promise; return route.fulfill({ status: 503, json: {} }); }
      return route.fulfill({ json: { status: 'success', message: 'E2E connection passed' } });
    });
    try {
      await page.setViewportSize({ width: 320, height: 1000 }); await page.goto(`/${locale}/settings?section=connections`);
      const button = page.getByRole('button', { name: copy.Settings.testConnection, exact: true });
      await button.focus(); await page.keyboard.press('Enter'); await expect(button).toBeDisabled(); await expect(button).toHaveAttribute('aria-busy', 'true');
      expect(calls).toBe(1); held.release(); await expect(page.getByText(copy.Settings.apiTestFailed, { exact: true })).toBeVisible(); await expect(button).toBeEnabled();
      await button.focus(); await page.keyboard.press('Space'); await expect(page.getByText('E2E connection passed', { exact: true })).toBeVisible(); expect(calls).toBe(2);
    } finally { held.release(); }
  });
}
