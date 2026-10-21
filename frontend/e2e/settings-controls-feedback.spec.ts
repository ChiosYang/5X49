import { expectAnnouncedOnly } from './settings-feedback-assertions';
import { test, expect, type Page } from '@playwright/test';
import path from 'node:path';
import en from '../messages/en.json';
import zh from '../messages/zh.json';

const backend = process.env.E2E_BACKEND!;
const gate = () => { let release!: () => void; const promise = new Promise<void>(resolve => { release = resolve; }); return { promise, release }; };
let roots: string[], originalRoots: string[];
async function choose(page: Page, copy: typeof en, section: keyof typeof en.SettingsArea) {
  await page.getByRole('button', { name: copy.SettingsArea.categories, exact: true }).click();
  await page.getByRole('dialog', { name: copy.Settings.settingsNavigation, exact: true }).getByRole('link', { name: copy.SettingsArea[section], exact: true }).click();
  await expect(page.locator(`#settings-title-${section}`)).toBeVisible();
}
async function leaveAndReturn(page: Page, copy: typeof en) {
  await choose(page, copy, 'library-maintenance');
  await page.getByRole('link', { name: copy.LibraryManagement.constellation.actions['review-metadata'].label, exact: true }).click();
  await expect(page).toHaveURL(/\/library\?.*view=metadata/);
  await page.goBack(); await expect(page.locator('#settings-title-library-maintenance')).toBeVisible();
  await choose(page, copy, 'connections');
}
async function capture(page: Page, name: string) {
  await page.evaluate(async () => { await document.fonts.ready; window.scrollTo(0, 0); });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: path.join('e2e-artifacts', name), fullPage: true, animations: 'disabled' });
}
test.beforeAll(async ({ request }) => {
  originalRoots = (await (await request.get(`${backend}/settings/media-dirs`)).json()).media_dirs;
  const fixture = await request.post(`${backend}/__e2e/control`, { headers: { 'x-e2e-token': process.env.E2E_TOKEN! }, data: { action: 'multi_root_fixture' } });
  expect(fixture.ok()).toBeTruthy(); roots = (await fixture.json()).roots;
});
test.afterAll(async ({ request }) => {
  expect((await request.put(`${backend}/settings/media-dirs`, { data: { media_dirs: originalRoots } })).ok()).toBeTruthy();
});
test.beforeEach(async ({ context, page, request }) => {
  expect((await request.put(`${backend}/settings/media-dirs`, { data: { media_dirs: [roots[0]] } })).ok()).toBeTruthy();
  await context.route('**/*', route => ['127.0.0.1', 'localhost'].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort('blockedbyclient'));
  let model = 'synthetic-model-a', url = 'https://synthetic.invalid/v1', key = 'synthetic-initial';
  await page.route('**/api/settings/model*', route => {
    if (route.request().method() === 'PUT') model = new URL(route.request().url()).searchParams.get('model_name')!;
    return route.fulfill({ json: { current_model: model, available_models: ['synthetic-model-a', 'synthetic-model-b'] } });
  });
  await page.route('**/api/settings/base-url*', route => {
    if (route.request().method() === 'PUT') url = new URL(route.request().url()).searchParams.get('base_url')!;
    return route.fulfill({ json: { base_url: url } });
  });
  await page.route('**/api/settings/tmdb', route => {
    if (route.request().method() === 'PUT') key = route.request().postDataJSON().api_key;
    return route.fulfill({ json: { status: 'success', configured: Boolean(key), source: key ? 'settings' : null } });
  });
});
for (const locale of ['en', 'zh'] as const) {
  const copy = locale === 'en' ? en : zh;
  test(`${locale} language uses the shared switch, fixed left loading slot, error and no Saved`, async ({ page }) => {
    const held = gate(); let calls = 0, saved = locale === 'en' ? 'zh' : 'en';
    await page.route('**/api/settings/language*', async route => {
      if (route.request().method() === 'PUT') {
        calls += 1; if (calls === 1) { await held.promise; return route.fulfill({ status: 503, json: {} }); }
        saved = new URL(route.request().url()).searchParams.get('language')!;
      }
      return route.fulfill({ json: { language: saved } });
    });
    try {
      await page.setViewportSize({ width: 320, height: 1000 }); await page.goto(`/${locale}/settings?section=general`);
      const group = page.getByRole('group', { name: copy.Settings.languagePref, exact: true }), control = group.getByRole('switch');
      await expect(control).toBeEnabled(); const before = (await control.boundingBox())!;
      await control.focus(); await page.keyboard.press('Space'); await expect(control).toBeDisabled();
      const spinner = group.locator('..').locator(':scope > span').first(); const loading = (await spinner.boundingBox())!;
      expect(loading.x + loading.width).toBeLessThan(before.x);
      expect((await control.boundingBox())!).toEqual(before); await capture(page, `feedback-${locale}-320-language-pending.png`);
      held.release(); await expect(page.getByText(copy.Settings.languageSaveFailed, { exact: true })).toBeVisible();
      await expect(control).toHaveAttribute('aria-checked', String(locale !== 'en'));
      await control.focus(); await page.keyboard.press('Enter'); await expect(control).toHaveAttribute('aria-checked', String(locale === 'en'));
      await expect(page.getByText(copy.Settings.saved, { exact: true })).toHaveCount(0);
      await expect(control).toHaveAccessibleName(copy.Settings.languageCurrent.replace('{language}', locale === 'en' ? 'English' : '中文'));
      await choose(page, copy, 'library');
      const other = page.getByRole('switch', { name: copy.Settings.autoScan, exact: true });
      const after = (await other.boundingBox())!; expect(before.height).toBe(after.height); expect(before.width).toBe(after.width);
    } finally { held.release(); }
  });

  test(`${locale} blank blur plus/remove, picker loading/error/cancel, Up and history never create an empty root`, async ({ page }) => {
    const payloads: string[][] = [];
    page.on('request', request => { if (request.method() === 'PUT' && request.url().endsWith('/api/settings/media-dirs')) payloads.push(request.postDataJSON().media_dirs); });
    await page.setViewportSize({ width: 320, height: 1000 }); await page.goto(`/${locale}/settings?section=general`); await choose(page, copy, 'library');
    const input = page.locator('#media-root-0'), add = page.getByRole('button', { name: copy.MediaRoots.addDirectory, exact: true });
    await expect(input).toHaveValue(roots[0]); await input.fill(''); await add.click();
    let dialog = page.getByRole('dialog', { name: copy.FileBrowser.title, exact: true });
    await expect(dialog.getByRole('button', { name: copy.FileBrowser.selectCurrent, exact: true })).toBeEnabled();
    await dialog.getByRole('button', { name: copy.FileBrowser.up }).click();
    await dialog.getByRole('button', { name: copy.FileBrowser.cancel, exact: true }).click();
    await expect(input).toHaveValue(roots[0]); await expect(page.locator('#media-root-1')).toHaveCount(0); expect(payloads).toEqual([]);
    const held = gate();
    await page.route('**/api/sys/list-dirs*', async route => { await held.promise; return route.fulfill({ status: 503, json: {} }); });
    try {
      await page.setViewportSize({ width: 320, height: 568 });
      await add.click(); dialog = page.getByRole('dialog', { name: copy.FileBrowser.title, exact: true });
      await expect(dialog.getByRole('button', { name: copy.FileBrowser.selectCurrent, exact: true })).toBeDisabled();
      held.release(); await expect(dialog.getByText(copy.FileBrowser.loadFailed, { exact: true })).toBeVisible();
      await expect(dialog.getByRole('button', { name: copy.FileBrowser.selectCurrent, exact: true })).toBeDisabled();
      const bounds = (await dialog.boundingBox())!;
      for (const name of [copy.FileBrowser.cancel, copy.FileBrowser.selectCurrent]) {
        const action = dialog.getByRole('button', { name, exact: true }), rect = (await action.boundingBox())!;
        expect(rect.x).toBeGreaterThanOrEqual(bounds.x); expect(rect.x + rect.width).toBeLessThanOrEqual(bounds.x + bounds.width);
        expect(rect.y).toBeGreaterThanOrEqual(bounds.y); expect(rect.y + rect.height).toBeLessThanOrEqual(Math.min(bounds.y + bounds.height, 568));
      }
      await capture(page, `feedback-${locale}-320-picker-error.png`); await page.keyboard.press('Escape'); await expect(add).toBeFocused();
    } finally { held.release(); }
    await page.setViewportSize({ width: 320, height: 1000 });
    await page.unroute('**/api/sys/list-dirs*');
    await add.click(); await expect(page.getByRole('dialog', { name: copy.FileBrowser.title, exact: true })).toBeVisible();
    await page.goBack(); await expect(page.locator('#settings-title-general')).toBeVisible();
    await expect(page.getByRole('dialog')).toHaveCount(0); expect(payloads).toEqual([]);
    await choose(page, copy, 'library'); await expect(input).toHaveValue(roots[0]); await input.fill('');
    await page.getByRole('button', { name: copy.MediaRoots.removeDirectory.replace('{number}', '1'), exact: true }).click();
    await expect.poll(() => payloads).toEqual([[]]); await expect(input).toHaveCount(0);
  });

  test(`${locale} clearing a queued root restores the latest completed path while saves stay serial`, async ({ page }) => {
    const held = gate(); const payloads: string[][] = []; const latest = path.join(process.env.E2E_ROOT!, 'normal/media');
    await page.route('**/api/settings/media-dirs', async route => {
      if (route.request().method() !== 'PUT') return route.continue();
      payloads.push(route.request().postDataJSON().media_dirs); if (payloads.length === 1) await held.promise;
      return route.fulfill({ response: await route.fetch() });
    });
    try {
      await page.goto(`/${locale}/settings?section=library`); const input = page.locator('#media-root-0');
      await expect(input).toHaveValue(roots[0]); await input.fill(roots[1]); await input.press('Enter'); await expect.poll(() => payloads.length).toBe(1);
      await input.fill(latest); await input.press('Enter'); await input.fill(''); await input.press('Tab'); await expect(input).toHaveValue(latest);
      held.release(); await expect.poll(() => payloads).toEqual([[roots[1]], [latest]]);
      await expectAnnouncedOnly(page.getByText(copy.MediaRoots.saved, { exact: true }), copy.MediaRoots.saved); await page.reload(); await expect(input).toHaveValue(latest);
    } finally { held.release(); }
  });

  test(`${locale} API result icons are right of the test and invalidate on URL/model edits and stale responses`, async ({ page }) => {
    const held = gate(); let tests = 0;
    await page.route('**/api/settings/test-api-key', async route => {
      tests += 1; if (tests === 1) await held.promise;
      return route.fulfill({ json: { status: 'success', message: 'PRIVATE synthetic response must not render' } });
    });
    try {
      await page.setViewportSize({ width: 320, height: 1000 }); await page.goto(`/${locale}/settings?section=connections`);
      const button = page.getByRole('button', { name: copy.Settings.testConnection, exact: true }), input = page.getByRole('textbox', { name: copy.Settings.baseUrl, exact: true });
      await expect(button).toBeEnabled(); await button.click(); await input.fill('https://new.invalid/v1'); await input.press('Enter');
      held.release(); await expect(button).toBeEnabled(); await expect(page.getByRole('img', { name: copy.Settings.connectionTestPassed, exact: true })).toHaveCount(0);
      await button.click(); const result = page.getByRole('img', { name: copy.Settings.connectionTestPassed, exact: true }); await expect(result).toBeVisible();
      const b = (await button.boundingBox())!, r = (await result.boundingBox())!; expect(r.x).toBeGreaterThanOrEqual(b.x + b.width);
      await result.focus(); await expect(page.getByRole('tooltip', { name: copy.Settings.connectionTestPassed, exact: true })).toBeVisible();
      await expect(page.getByText('PRIVATE synthetic response must not render', { exact: true })).toHaveCount(0); await capture(page, `feedback-${locale}-320-api-result.png`);
      await input.fill('https://draft.invalid/v1'); await expect(result).toHaveCount(0); await expect(button).toBeDisabled(); expect(tests).toBe(2);
      await input.press('Enter'); await expect(button).toBeEnabled(); await button.click(); await expect(result).toBeVisible();
      await page.getByRole('group', { name: copy.Settings.model, exact: true }).locator('button[aria-expanded]').click();
      await page.getByRole('button', { name: 'synthetic-model-b', exact: true }).click();
      await expect(result).toHaveCount(0); await expect(button).toBeEnabled(); expect(tests).toBe(3);
    } finally { held.release(); }
  });

  test(`${locale} environment-owned TMDB keys remain read-only and loading errors remain actionable`, async ({ page }) => {
    let fail = false; const writes: string[] = [];
    await page.route('**/api/settings/tmdb', route => {
      if (route.request().method() !== 'GET') writes.push(route.request().method());
      return fail ? route.fulfill({ status: 503, json: {} }) : route.fulfill({ json: { configured: true, source: 'environment' } });
    });
    await page.goto(`/${locale}/settings?section=connections`);
    const input = page.getByLabel(copy.Settings.tmdbApiKey, { exact: true }), button = page.getByRole('button', { name: copy.Settings.tmdbTestBtn, exact: true });
    await expect(input).toBeDisabled(); await expect(button).toBeEnabled();
    await expect(page.getByText(copy.Settings.tmdbSourceEnvironment, { exact: true })).toBeVisible();
    fail = true; await page.reload(); await expect(page.getByText(copy.Settings.tmdbLoadFailed, { exact: true })).toBeVisible();
    await expect(input).toBeDisabled(); await expect(button).toBeDisabled(); expect(writes).toEqual([]);
  });

  test(`${locale} TMDB pending autosave and latest queue survive leaving Settings and remounting`, async ({ page }) => {
    const held = gate(); const payloads: string[] = []; let saved = 'synthetic-initial', active = 0, maximum = 0, tests = 0;
    await page.route('**/api/settings/tmdb', async route => {
      if (route.request().method() === 'PUT') {
        const key = route.request().postDataJSON().api_key; payloads.push(key); active += 1; maximum = Math.max(maximum, active);
        if (payloads.length === 1) await held.promise;
        saved = key; active -= 1;
      }
      return route.fulfill({ json: { status: 'success', configured: Boolean(saved), source: saved ? 'settings' : null } });
    });
    await page.route('**/api/settings/tmdb/test', route => { tests += 1; return route.fulfill({ json: { status: 'success' } }); });
    try {
      await page.setViewportSize({ width: 320, height: 1000 }); await page.goto(`/${locale}/settings?section=connections`);
      const key = page.getByLabel(copy.Settings.tmdbApiKey, { exact: true }), button = page.getByRole('button', { name: copy.Settings.tmdbTestBtn, exact: true });
      await expect(key).toBeEnabled(); await key.fill('synthetic-a'); expect(payloads).toEqual([]); await key.press('Enter'); await expect.poll(() => payloads.length).toBe(1);
      await key.fill('synthetic-c'); await key.press('Enter'); await leaveAndReturn(page, copy);
      await expect(key).toHaveValue('synthetic-c'); await expect(button).toBeDisabled();
      await key.fill('synthetic-b'); await key.press('Enter'); expect(payloads).toEqual(['synthetic-a']);
      await capture(page, `feedback-${locale}-320-tmdb-pending.png`); held.release();
      await expect.poll(() => payloads).toEqual(['synthetic-a', 'synthetic-b']); await expect(key).toHaveValue('');
      await expect(button).toBeEnabled(); expect(saved).toBe('synthetic-b'); expect(maximum).toBe(1); expect(tests).toBe(0);
      await page.reload(); await expect(button).toBeEnabled(); await expect(key).toHaveValue('');
    } finally { held.release(); }
  });

  test(`${locale} TMDB failed save keeps newer input across remount, retries and shows no Save or success prose`, async ({ page }) => {
    const held = gate(); let fail = true; const payloads: string[] = [];
    await page.route('**/api/settings/tmdb', async route => {
      if (route.request().method() !== 'PUT') return route.fallback();
      payloads.push(route.request().postDataJSON().api_key); if (payloads.length === 1) await held.promise;
      return fail ? route.fulfill({ status: 503, json: { detail: 'secret synthetic response' } }) : route.fulfill({ json: { status: 'success', configured: true, source: 'settings' } });
    });
    try {
      await page.setViewportSize({ width: 320, height: 1000 }); await page.goto(`/${locale}/settings?section=connections`);
      const key = page.getByLabel(copy.Settings.tmdbApiKey, { exact: true });
      await expect(key).toBeEnabled(); await key.fill('synthetic-first'); await key.press('Enter'); await expect.poll(() => payloads.length).toBe(1);
      await key.fill('synthetic-latest'); await key.press('Enter'); await leaveAndReturn(page, copy); held.release();
      await expect(page.getByText(copy.Settings.tmdbSaveFailed, { exact: true })).toBeVisible(); await expect(key).toHaveValue('synthetic-latest');
      await leaveAndReturn(page, copy); await expect(key).toHaveValue('synthetic-latest');
      await expect(page.getByText(copy.Settings.tmdbSaveFailed, { exact: true })).toBeVisible();
      await expect(page.getByText('secret synthetic response', { exact: true })).toHaveCount(0);
      await expect(page.getByRole('button', { name: copy.Settings.save, exact: true })).toHaveCount(0);
      await capture(page, `feedback-${locale}-320-tmdb-failed.png`);
      fail = false; await page.getByRole('button', { name: copy.Settings.retrySave, exact: true }).click();
      await expect(key).toHaveValue(''); expect(payloads).toEqual(['synthetic-first', 'synthetic-latest']);
      await expectAnnouncedOnly(page.getByText(copy.Settings.saved, { exact: true }), copy.Settings.saved);
    } finally { held.release(); }
  });

  test(`${locale} TMDB unsaved/pending edits block tests, invalidate stale results and allow explicit blank clearing`, async ({ page }) => {
    const firstTest = gate(), save = gate(); let tests = 0; const payloads: string[] = [];
    await page.route('**/api/settings/tmdb/test', async route => {
      tests += 1; if (tests === 1) await firstTest.promise;
      return route.fulfill({ json: { status: tests === 3 ? 'error' : 'success', message: 'PRIVATE synthetic test response' } });
    });
    await page.route('**/api/settings/tmdb', async route => {
      if (route.request().method() !== 'PUT') return route.fallback();
      const key = route.request().postDataJSON().api_key; payloads.push(key); await save.promise;
      return route.fulfill({ json: { status: 'success', configured: Boolean(key), source: key ? 'settings' : null } });
    });
    try {
      await page.setViewportSize({ width: 320, height: 1000 }); await page.goto(`/${locale}/settings?section=connections`);
      const key = page.getByLabel(copy.Settings.tmdbApiKey, { exact: true }), button = page.getByRole('button', { name: copy.Settings.tmdbTestBtn, exact: true });
      await expect(button).toBeEnabled(); expect(await button.textContent()).toBe(''); await key.focus(); await key.press('Tab'); expect(payloads).toEqual([]);
      await button.click(); await key.fill('synthetic-new'); firstTest.release(); await expect(button).toBeDisabled();
      await expect(page.getByRole('img', { name: copy.Settings.connectionTestPassed, exact: true })).toHaveCount(0); expect(payloads).toEqual([]);
      await key.press('Enter'); await expect.poll(() => payloads.length).toBe(1); await expect(button).toBeDisabled(); expect(tests).toBe(1);
      save.release(); await expect(key).toHaveValue(''); await expect(button).toBeEnabled(); await button.click();
      const result = page.getByRole('img', { name: copy.Settings.connectionTestPassed, exact: true }); await expect(result).toBeVisible();
      const b = (await button.boundingBox())!, r = (await result.boundingBox())!; expect(r.x).toBeGreaterThanOrEqual(b.x + b.width);
      await result.focus(); await expect(page.getByRole('tooltip', { name: copy.Settings.connectionTestPassed, exact: true })).toBeVisible();
      await expect(page.getByText('PRIVATE synthetic test response', { exact: true })).toHaveCount(0);
      await button.click(); const failure = page.getByRole('img', { name: copy.Settings.connectionTestFailed, exact: true }); await expect(failure).toBeVisible(); await failure.focus();
      await expect(page.getByRole('tooltip', { name: copy.Settings.connectionTestFailed, exact: true })).toBeVisible(); await capture(page, `feedback-${locale}-320-tmdb-test-failed.png`);
      await key.fill(' '); await key.press('Tab'); await expect.poll(() => payloads).toEqual(['synthetic-new', '']); await expect(button).toBeDisabled(); await expect(failure).toHaveCount(0); expect(tests).toBe(3);
    } finally { firstTest.release(); save.release(); }
  });
}
