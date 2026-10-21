import { test, expect, type APIRequestContext, type Page } from '@playwright/test';
import path from 'node:path';
import en from '../messages/en.json';
import zh from '../messages/zh.json';
import { settingSections, type SettingSection } from '../src/lib/settings-navigation';
import type { HealthConfig } from '../src/lib/video-health';
import type { WorkflowRunView } from '../src/types/movie';

const backend = process.env.E2E_BACKEND!;
const copies = { en, zh };
let roots: string[], originalRoots: string[], originalHealth: HealthConfig, originalLanguage: string;
async function read(request: APIRequestContext, endpoint: string) {
  const response = await request.get(`${backend}${endpoint}`); expect(response.ok()).toBeTruthy(); return response.json();
}
async function control(request: APIRequestContext, action: string, extra = {}) {
  const response = await request.post(`${backend}/__e2e/control`, { headers: { 'x-e2e-token': process.env.E2E_TOKEN! }, data: { action, ...extra } });
  expect(response.ok()).toBeTruthy(); return response.json();
}
async function choose(page: Page, locale: 'en' | 'zh', width: number, section: SettingSection) {
  const copy = copies[locale];
  if (width < 768) {
    await page.getByRole('button', { name: copy.SettingsArea.categories, exact: true }).click();
    const dialog = page.getByRole('dialog', { name: copy.Settings.settingsNavigation, exact: true });
    await dialog.getByRole('link', { name: copy.SettingsArea[section], exact: true }).click();
    await expect(dialog).toHaveCount(0);
  } else await page.getByRole('navigation', { name: copy.Settings.settingsNavigation, exact: true }).getByRole('link', { name: copy.SettingsArea[section], exact: true }).click();
  await expect(page.locator(`#settings-title-${section}`)).toBeVisible();
  await expect.poll(() => new URL(page.url()).searchParams.get('section')).toBe(section);
}
test.beforeAll(async ({ request }) => {
  originalRoots = (await read(request, '/settings/media-dirs')).media_dirs;
  originalLanguage = (await read(request, '/settings/language')).language;
  const { enabled, paused, start_minute, end_minute, daily_budget_minutes } = (await read(request, '/maintenance/video-health')).config;
  originalHealth = { enabled, paused, start_minute, end_minute, daily_budget_minutes };
  roots = (await control(request, 'multi_root_fixture')).roots;
});
test.afterAll(async ({ request }) => {
  expect((await request.put(`${backend}/settings/media-dirs`, { data: { media_dirs: originalRoots } })).ok()).toBeTruthy();
  expect((await request.put(`${backend}/maintenance/video-health/config`, { data: originalHealth })).ok()).toBeTruthy();
  expect((await request.put(`${backend}/settings/language`, { params: { language: originalLanguage } })).ok()).toBeTruthy();
});
test.beforeEach(async ({ context, request }) => {
  expect((await request.put(`${backend}/settings/media-dirs`, { data: { media_dirs: [roots[0]] } })).ok()).toBeTruthy();
  expect((await request.put(`${backend}/maintenance/video-health/config`, { data: { enabled: true, paused: true } })).ok()).toBeTruthy();
  await context.route('**/*', route => ['127.0.0.1', 'localhost'].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort('blockedbyclient'));
});

for (const locale of ['en', 'zh'] as const) {
  const copy = copies[locale];
  for (const width of [1440, 390, 320]) {
    test(`${locale} all eight categories and secondary groups at ${width}px enter without actions`, async ({ page }) => {
      test.setTimeout(180000);
      const writes: string[] = [], errors: string[] = [];
      page.on('pageerror', error => errors.push(error.message));
      page.on('request', request => {
        const url = new URL(request.url());
        if (url.pathname.startsWith('/api/') && (request.method() !== 'GET' || url.pathname === '/api/diagnostics/providers')) writes.push(url.pathname);
      });
      await page.setViewportSize({ width, height: 1000 });
      await page.goto(`/${locale}/settings`);
      await expect(page.getByRole('button', { name: 'zh', exact: true })).toBeVisible();
      await expect(page.getByText(copy.Settings.roadmap, { exact: true })).toHaveCount(0);
      if (width < 768) await page.getByRole('button', { name: copy.SettingsArea.categories, exact: true }).click();
      const nav = page.getByRole('navigation', { name: copy.Settings.settingsNavigation, exact: true });
      await expect(nav.getByRole('link')).toHaveText(settingSections.map(section => copy.SettingsArea[section]));
      if (width < 768) { await page.keyboard.press('Escape'); await expect(page.getByRole('dialog')).toHaveCount(0); }
      for (const section of settingSections) {
        await choose(page, locale, width, section);
        await page.evaluate(() => document.fonts.ready);
        await expect(page.getByRole('heading', { level: 1 })).toHaveText(copy.Settings.title);
        await expect(page.getByRole('heading', { level: 2 })).toHaveText(copy.SettingsArea[section]);
        await expect(page.getByRole('tab')).toHaveCount(0);
        if (section === 'general') await expect(page.getByRole('button', { name: originalLanguage, exact: true })).toHaveAttribute('aria-pressed', 'true');
        else if (section === 'library') {
          await expect(page.locator('#media-root-0')).toHaveValue(roots[0]);
          await expect(page.getByRole('heading', { name: copy.SettingsArea.scanRules, exact: true })).toBeVisible();
          await expect(page.getByRole('heading', { name: copy.SettingsArea.metadataArtwork, exact: true })).toBeVisible();
          await expect(page.getByRole('switch', { name: copy.VideoHealth.automatic, exact: true })).toBeVisible();
          await expect(page.getByRole('switch', { name: copy.VideoHealth.automatic, exact: true })).toHaveAttribute('aria-checked', 'true');
          await expect(page.getByRole('button', { name: copy.VideoHealth.queue, exact: true })).toHaveCount(0);
          await expect(page.getByRole('button', { name: copy.MediaRoots.scanAll, exact: true })).toHaveCount(0);
        } else if (section === 'connections') {
          await expect(page.getByRole('heading', { name: copy.Settings.aiProvider, exact: true })).toBeVisible();
          await expect(page.getByRole('heading', { name: copy.Settings.tmdbIntegration, exact: true })).toBeVisible();
          await expect(page.getByRole('textbox', { name: copy.Settings.baseUrl, exact: true })).not.toHaveValue('');
        } else if (section === 'library-maintenance') {
          await expect(page.getByRole('button', { name: copy.MediaRoots.scanAll, exact: true })).toBeVisible();
          await expect(page.getByRole('button', { name: copy.LibraryManagement.constellation.actions['scrape-metadata'].label, exact: true })).toBeVisible();
          await expect(page.getByRole('heading', { name: copy.LibraryCare.offlineTitle, exact: true })).toBeVisible();
        } else if (section === 'video-checks') {
          await expect(page.getByRole('heading', { name: copy.VideoHealth.controls, exact: true })).toBeVisible();
          await expect(page.getByRole('heading', { name: copy.VideoHealth.results, exact: true })).toBeVisible();
          const controls = page.locator('section[aria-labelledby="video-health-controls"]');
          await expect(controls.getByRole('button', { name: copy.VideoHealth.queue, exact: true })).toBeVisible();
          for (const button of await controls.getByRole('button').all()) expect(await button.evaluate(element => element.getBoundingClientRect().right <= element.parentElement!.getBoundingClientRect().right + 1)).toBe(true);
          await expect(page.getByRole('switch', { name: copy.VideoHealth.automatic, exact: true })).toHaveCount(0);
          await expect(page.locator('#video-health').getByText(copy.VideoHealth.loading, { exact: true })).toHaveCount(0);
          await expect(page.locator('#video-health').getByRole('alert')).toHaveCount(0);
          await expect(page.locator('section:not([hidden]) input[type="time"]')).toHaveCount(0);
        } else if (section === 'diagnostics') {
          await expect(page.getByRole('heading', { name: copy.SettingsArea.localChecks, exact: true })).toBeVisible();
          await expect(page.getByRole('heading', { name: copy.SettingsArea.runtime, exact: true })).toBeVisible();
          await expect(page.getByText(copy.Maintenance.loading, { exact: true })).toHaveCount(0);
        } else if (section === 'backup') {
          await expect(page.getByRole('heading', { name: copy.MaintenanceBackup.title, exact: true })).toBeVisible();
          await expect(page.getByText(copy.MaintenanceBackup.exclusions, { exact: true })).toBeVisible();
          await expect(page.getByText(copy.Maintenance.backupPrivacy, { exact: true })).toBeVisible();
          await expect(page.getByRole('button', { name: copy.MaintenanceBackup.create, exact: true })).toBeEnabled();
        } else if (section === 'cleanup') await expect(page.getByText(copy.LibraryCare.danger.clearDesc, { exact: true })).toBeVisible();
        await page.evaluate(() => window.scrollTo(0, 0));
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await expect(page.locator('nav.navigation-bar')).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)');
        await page.screenshot({ path: `e2e-artifacts/organization-${locale}-${width}-${section}.png`, fullPage: true, animations: 'disabled' });
      }
      expect(writes).toEqual([]); expect(errors).toEqual([]);
    });
  }

  test(`${locale} keyboard picker, history and unsaved directory/service drafts retain their semantics`, async ({ page, request }) => {
    await page.setViewportSize({ width: 320, height: 1000 });
    await page.goto(`/${locale}/settings`);
    const picker = page.getByRole('button', { name: copy.SettingsArea.categories, exact: true });
    await picker.focus(); await page.keyboard.press('Enter');
    const dialog = page.getByRole('dialog', { name: copy.Settings.settingsNavigation, exact: true });
    await expect(dialog.getByRole('link', { name: copy.SettingsArea.general, exact: true })).toBeFocused();
    await page.keyboard.press('Shift+Tab');
    await expect(dialog.getByRole('link', { name: copy.SettingsArea.cleanup, exact: true })).toBeFocused();
    await page.keyboard.press('Escape'); await expect(picker).toBeFocused();
    await choose(page, locale, 320, 'library');
    await page.locator('#media-root-0').fill('unfinished');
    await choose(page, locale, 320, 'library-maintenance');
    await expect(page.getByRole('button', { name: copy.MediaRoots.scanAll, exact: true })).toBeDisabled();
    await expect(page.getByText(copy.SettingsArea.pendingDirectories, { exact: false })).toBeVisible();
    await page.goBack(); await expect(page.locator('#media-root-0')).toHaveValue('unfinished');
    await page.goForward(); await expect(page.getByRole('button', { name: copy.MediaRoots.scanAll, exact: true })).toBeDisabled();
    expect((await read(request, '/settings/media-dirs')).media_dirs).toEqual([roots[0]]);
    await choose(page, locale, 320, 'library');
    await page.getByRole('button', { name: copy.MediaRoots.discard, exact: true }).click();
    await choose(page, locale, 320, 'library-maintenance');
    await expect(page.getByRole('button', { name: copy.MediaRoots.scanAll, exact: true })).toBeEnabled();
    await choose(page, locale, 320, 'library');
    await page.locator('#media-root-0').fill(roots[1]);
    await page.locator('#media-root-0').press('Enter');
    await expect(page.getByText(copy.MediaRoots.saved, { exact: true })).toBeVisible();
    await choose(page, locale, 320, 'library-maintenance');
    await expect(page.getByRole('button', { name: copy.MediaRoots.scanAll, exact: true })).toBeEnabled();
    expect((await read(request, '/settings/media-dirs')).media_dirs).toEqual([roots[1]]);
    await choose(page, locale, 320, 'connections');
    await page.getByRole('textbox', { name: copy.Settings.baseUrl, exact: true }).fill('https://');
    await choose(page, locale, 320, 'general');
    await page.goBack(); await expect(page.getByRole('textbox', { name: copy.Settings.baseUrl, exact: true })).toHaveValue('https://');
    expect((await read(request, '/settings/base-url')).base_url).not.toBe('https://');
    await page.reload(); await expect(page.getByRole('textbox', { name: copy.Settings.baseUrl, exact: true })).not.toHaveValue('https://');
  });

  test(`${locale} directory drafts block only scan retries until Discard or completed input`, async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 1000 });
    const scans = ['library.reconcile', 'library.scan_folder', 'library.refresh_item'];
    const others = ['library.mark_path_missing', 'library.resolve_relink', 'metadata.scrape_library', 'organizer.organize_root', 'external_scores.refresh_library'];
    const workflow = (type: string, index: number, status: WorkflowRunView['status']): WorkflowRunView => ({
      id: `guard_${index}`, type, status, definition_version: `${type}.v1`, subject_type: 'library',
      result_summary: `Guard ${type} ${status}`, cancel_requested: false, steps: [],
      created_at: '2026-10-20T00:00:00Z', updated_at: '2026-10-20T00:00:00Z',
    });
    const records = [...scans, ...others].map((type, index) => workflow(type, index, index % 2 ? 'cancelled' : 'failed'));
    const active = workflow('library.reconcile', records.length, 'running');
    const operations: Array<{ id: string; operation: string }> = [];
    await page.route(/\/api\/workflows(?:\?|$)/, route => route.fulfill({ json: [...records, active] }));
    await page.route(/\/api\/workflows\/guard_\d+\/(?:retry|cancel)$/, route => {
      const [id, operation] = new URL(route.request().url()).pathname.split('/').slice(-2);
      operations.push({ id, operation });
      return route.fulfill({ status: 202, json: { workflow_id: id } });
    });
    await page.goto(`/${locale}/settings?section=library`);
    await expect(page.locator('#media-root-0')).toHaveValue(roots[0]);
    await page.locator('#media-root-0').fill('unfinished');
    await choose(page, locale, 320, 'library-maintenance');
    const tasks = page.getByRole('region', { name: copy.SettingsArea.recentWorkflows, exact: true });
    const retry = (record: WorkflowRunView) => tasks.getByRole('listitem').filter({ hasText: record.result_summary! }).getByRole('button', { name: copy.LibraryManagement.constellation.retryWorkflow, exact: true });
    for (const record of records.slice(0, scans.length)) await expect(retry(record)).toBeDisabled();
    expect(operations).toEqual([]);
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: path.join('e2e-artifacts', `organization-${locale}-320-scan-retry-guard.png`), fullPage: true, animations: 'disabled' });
    for (const record of records.slice(scans.length)) {
      await expect(retry(record)).toBeEnabled(); await retry(record).click();
      await expect.poll(() => operations.filter(operation => operation.id === record.id && operation.operation === 'retry').length).toBe(1);
    }
    const cancel = tasks.getByRole('listitem').filter({ hasText: active.result_summary! }).getByRole('button', { name: copy.LibraryManagement.constellation.cancelWorkflow, exact: true });
    await expect(cancel).toBeEnabled(); await cancel.click();
    await expect.poll(() => operations.filter(operation => operation.operation === 'cancel').length).toBe(1);
    expect(operations.filter(operation => records.slice(0, scans.length).some(record => record.id === operation.id))).toEqual([]);

    for (const resolution of ['discard', 'save'] as const) {
      await choose(page, locale, 320, 'library');
      if (resolution === 'discard') await page.getByRole('button', { name: copy.MediaRoots.discard, exact: true }).click();
      else { await page.locator('#media-root-0').fill(roots[1]); await page.locator('#media-root-0').press('Enter'); await expect(page.getByText(copy.MediaRoots.saved, { exact: true })).toBeVisible(); }
      await choose(page, locale, 320, 'library-maintenance');
      for (const record of records.slice(0, scans.length)) {
        await expect(retry(record)).toBeEnabled(); await retry(record).click();
        await expect.poll(() => operations.filter(operation => operation.id === record.id).length).toBe(resolution === 'discard' ? 1 : 2);
      }
      if (resolution === 'discard') {
        await choose(page, locale, 320, 'library');
        await page.locator('#media-root-0').fill('unfinished');
        await choose(page, locale, 320, 'library-maintenance');
        for (const record of records.slice(0, scans.length)) await expect(retry(record)).toBeDisabled();
      }
    }
  });

  test(`${locale} legacy entries resolve to one category and preserve their functional anchors`, async ({ page }) => {
    const cases: Array<[string, string, string]> = [
      ['/library/manage', 'library-maintenance', ''], ['/library/manage#video-health', 'video-checks', '#video-health'],
      ['/library/manage#backup-heading', 'backup', '#backup-download'], ['/admin/health', 'diagnostics', ''],
      ['/settings?section=integrations', 'connections', ''], ['/settings?section=maintenance', 'diagnostics', ''],
      ['/settings?section=library#danger-zone', 'cleanup', '#danger-zone'], ['/settings?section=maintenance#restore', 'backup', '#restore'],
    ];
    for (const [entry, section, hash] of cases) {
      await page.goto(`/${locale}${entry}`);
      await expect.poll(() => new URL(page.url()).searchParams.get('section')).toBe(section);
      await expect(page.locator(`#settings-title-${section}`)).toBeVisible();
      expect(new URL(page.url()).hash).toBe(hash);
      await page.reload(); await expect(page.locator(`#settings-title-${section}`)).toBeVisible();
    }
    for (const [anchor, view] of [['metadata-reviews', 'metadata'], ['root-video-reviews', 'inbox']]) {
      await page.goto(`/${locale}/library/manage#${anchor}`);
      await expect.poll(() => new URL(page.url()).searchParams.get('view')).toBe(view);
    }
  });

  test(`${locale} diagnostic failures/probes and cleanup confirmation retain safe boundaries`, async ({ page }) => {
    const diagnostics = /\/api\/diagnostics$/;
    await page.route(diagnostics, route => route.fulfill({ status: 503, json: {} }));
    await page.goto(`/${locale}/settings?section=diagnostics`);
    await expect(page.getByText(copy.Maintenance.backendUnavailable, { exact: true })).toBeVisible();
    await page.unroute(diagnostics); await page.reload();
    let failProbe = true;
    await page.route('**/api/diagnostics/providers', route => failProbe ? route.fulfill({ status: 503, json: {} }) : route.fulfill({ json: { tmdb: { state: 'tls_failed' }, artwork: { state: 'connection_failed' } } }));
    await page.getByRole('button', { name: copy.Maintenance.checkProviders, exact: true }).click();
    await expect(page.getByText(copy.Maintenance.providerCheckFailed, { exact: true })).toBeVisible();
    failProbe = false;
    await page.getByRole('button', { name: copy.Maintenance.checkProviders, exact: true }).click();
    await expect(page.getByText(copy.Maintenance.state_tls_failed, { exact: false })).toBeVisible();
    const workflowUrl = /\/api\/workflows(?:\?|$)/;
    await page.route(workflowUrl, route => route.fulfill({ status: 503, json: {} }));
    await page.goto(`/${locale}/settings?section=cleanup`);
    await expect(page.getByText(copy.LibraryCare.danger.workflowUnavailable, { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: copy.LibraryCare.danger.clearButton, exact: true })).toBeDisabled();
    await page.unroute(workflowUrl); await page.route(workflowUrl, route => route.fulfill({ json: [] }));
    await page.reload();
    await page.getByRole('button', { name: copy.LibraryCare.danger.clearButton, exact: true }).click();
    const confirmation = page.getByRole('dialog');
    const confirm = confirmation.getByRole('button', { name: copy.LibraryCare.danger.confirm, exact: true });
    await expect(confirm).toBeDisabled();
    await confirmation.getByRole('textbox').fill('wrong'); await expect(confirm).toBeDisabled();
    await confirmation.getByRole('textbox').fill(copy.LibraryCare.danger.phrase); await expect(confirm).toBeEnabled();
    await page.keyboard.press('Escape'); await expect(confirmation).toHaveCount(0);
    await choose(page, locale, 390, 'general');
    await choose(page, locale, 390, 'cleanup');
    await page.getByRole('button', { name: copy.LibraryCare.danger.clearButton, exact: true }).click();
    await expect(confirmation).toBeVisible();
    await page.goBack();
    await expect(page.locator('#settings-title-general')).toBeVisible();
    await expect(confirmation).toHaveCount(0);
    await expect(page.locator('body')).not.toHaveCSS('overflow', 'hidden');
    await expect(page.getByRole('button', { name: 'en', exact: true })).toBeEnabled();
    await page.goForward();
    await expect(page.getByRole('button', { name: copy.LibraryCare.danger.clearButton, exact: true })).toBeEnabled();
    await expect(confirmation).toHaveCount(0);
  });

  test(`${locale} video result filter/page/detail survive refresh, Film return and retry`, async ({ page, request }) => {
    const fixture = await control(request, 'matching_fixture', { name: `settings-return-${locale}` });
    const file = (index: number) => ({ id: `health_mock_${index}`, asset_id: `asset_${index}`, film_id: fixture.target_id, library_item_id: null,
      title: `Inspection ${index}`, filename: `video-${index}.mp4`, status: 'abnormal', container_status: 'abnormal', decode_status: 'incomplete',
      current: true, version_key: `version_${index}`, version: { size: 123, mtime_ns: 1 }, decoded_seconds: 0, duration_seconds: 10, checked_at: null,
      error_code: null, error_summary: null, unread: true });
    await page.route(/\/api\/maintenance\/video-health\/files\?/, route => {
      const offset = Number(new URL(route.request().url()).searchParams.get('offset'));
      return route.fulfill({ json: { items: Array.from({ length: Math.min(20, 26 - offset) }, (_, index) => file(index + offset)), total: 26 } });
    });
    const actions: object[] = [];
    await page.route('**/api/maintenance/video-health/files/health_mock_*', route => {
      if (route.request().method() === 'POST') { actions.push(route.request().postDataJSON()); return route.fulfill({ json: { status: 'accepted' } }); }
      return route.fulfill({ json: file(Number(route.request().url().split('_').at(-1))) });
    });
    await page.goto(`/${locale}/settings?section=video-checks`);
    const results = page.locator('#video-health');
    await results.getByRole('combobox', { name: copy.VideoHealth.filter, exact: true }).selectOption('all');
    await expect.poll(() => new URL(page.url()).searchParams.get('health_state')).toBe('all');
    await results.getByRole('button', { name: copy.VideoHealth.next, exact: true }).click();
    await expect.poll(() => new URL(page.url()).searchParams.get('health_offset')).toBe('20');
    await expect(results.getByText('Inspection 20 · video-20.mp4', { exact: true })).toBeVisible();
    await results.getByRole('button', { name: copy.VideoHealth.details, exact: true }).first().click();
    await expect.poll(() => new URL(page.url()).searchParams.get('health_file')).toBe('health_mock_20');
    await expect(results.getByRole('button', { name: copy.VideoHealth.retry, exact: true })).toBeVisible();
    await page.reload();
    await expect(results.getByRole('combobox', { name: copy.VideoHealth.filter, exact: true })).toHaveValue('all');
    await expect(results.getByText('Inspection 20 · video-20.mp4', { exact: true })).toHaveCount(2);
    await results.getByRole('button', { name: copy.VideoHealth.retry, exact: true }).click();
    await expect.poll(() => actions.length).toBe(1); expect(actions).toEqual([{ action: 'retry' }]);
    const source = new URL(page.url()).search;
    await results.getByRole('link', { name: copy.VideoHealth.film, exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/library/${fixture.target_id}`));
    await page.goBack();
    await expect.poll(() => new URL(page.url()).search).toBe(source);
    await expect(page.locator('#video-health').getByRole('button', { name: copy.VideoHealth.retry, exact: true })).toBeVisible();
  });
}

test('language saves preserve the selected category and URL context', async ({ page, request }) => {
  expect((await request.put(`${backend}/settings/language`, { params: { language: 'en' } })).ok()).toBeTruthy();
  await page.goto('/en/settings?section=general&context=library');
  let reject = true;
  await page.route(/\/api\/settings\/language\?/, route => route.request().method() === 'PUT' && reject ? route.fulfill({ status: 503, json: {} }) : route.continue());
  await expect(page.getByRole('button', { name: 'en', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('button', { name: 'zh', exact: true }).click();
  await expect(page.getByText(en.Settings.languageSaveFailed, { exact: true })).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  expect((await read(request, '/settings/language')).language).toBe('en');
  reject = false;
  await page.getByRole('button', { name: 'zh', exact: true }).click();
  await expect(page.locator('html')).toHaveAttribute('lang', 'zh');
  await expect(page.getByRole('button', { name: 'zh', exact: true })).toHaveAttribute('aria-pressed', 'true');
  expect(new URL(page.url()).searchParams.get('section')).toBe('general');
  expect(new URL(page.url()).searchParams.get('context')).toBe('library');
});

test('maintenance scan uses saved synthetic roots and exposes the existing review/task operations', async ({ page, request }) => {
  expect((await request.put(`${backend}/settings/media-dirs`, { data: { media_dirs: [path.join(process.env.E2E_ROOT!, 'normal/media')] } })).ok()).toBeTruthy();
  await page.route('**/api/settings/tmdb', route => route.fulfill({ json: { configured: true, source: 'settings' } }));
  const operations: Array<{ path: string; body: unknown }> = [];
  let scoreFails = true;
  for (const endpoint of ['/api/library/scrape', '/api/library/external-scores/refresh']) await page.route(url => url.pathname === endpoint, route => {
    operations.push({ path: endpoint, body: route.request().postDataJSON() });
    return endpoint.endsWith('refresh') && scoreFails ? route.fulfill({ status: 503, json: {} }) : route.fulfill({ status: 202, json: { workflow_id: 'fixture-operation' } });
  });
  await page.goto('/en/settings?section=library-maintenance');
  const queued = page.waitForResponse(response => response.request().method() === 'POST' && response.url().endsWith('/api/library/scan'));
  await page.getByRole('button', { name: en.MediaRoots.scanAll, exact: true }).click();
  const response = await queued; expect(response.ok()).toBeTruthy();
  const id = (await response.json()).workflow_id;
  await expect.poll(async () => (await read(request, `/workflows/${id}`)).status, { timeout: 45000 }).toBe('succeeded');
  expect((await read(request, '/library/sync/status')).sync.last_result.complete).toBe(true);
  await expect(page.getByRole('link', { name: en.LibraryManagement.constellation.actions['review-metadata'].label, exact: true })).toHaveAttribute('href', '/en/library?view=metadata');
  await expect(page.getByRole('link', { name: en.LibraryManagement.constellation.actions['organize-files'].label, exact: true })).toHaveAttribute('href', '/en/library?view=inbox');
  await expect(page.getByRole('heading', { name: en.SettingsArea.recentWorkflows, exact: true })).toBeVisible();
  await page.getByRole('button', { name: en.LibraryManagement.constellation.actions['scrape-metadata'].label, exact: true }).click();
  await expect(page.getByText(en.LibraryManagement.constellation.feedback.scrape, { exact: true })).toBeVisible();
  await page.getByRole('button', { name: en.LibraryManagement.constellation.actions['refresh-scores'].label, exact: true }).click();
  await expect(page.getByText('Failed to start external score refresh', { exact: true })).toBeVisible();
  scoreFails = false;
  await page.getByRole('button', { name: en.LibraryManagement.constellation.actions['refresh-scores'].label, exact: true }).click();
  await expect(page.getByText(en.LibraryManagement.constellation.feedback.scores, { exact: true })).toBeVisible();
  expect(operations.map(operation => operation.path)).toEqual(['/api/library/scrape', '/api/library/external-scores/refresh', '/api/library/external-scores/refresh']);
  expect(operations[0].body).toEqual({ scope: 'unscraped', overwrite: false, write_nfo: true, download_artwork: true });

  let workflow = { ...await read(request, `/workflows/${id}`), status: 'failed', error_message: 'E2E failed task', result_summary: null };
  let retryFails = true;
  await page.route(/\/api\/workflows(?:\?|$)/, route => route.fulfill({ json: [workflow] }));
  await page.route(`**/api/workflows/${id}/retry`, route => {
    if (retryFails) return route.fulfill({ status: 503, json: { detail: 'E2E retry failed' } });
    workflow = { ...workflow, status: 'queued', error_message: null, result_summary: null, current_step: null, steps: [], cancel_requested: false };
    return route.fulfill({ status: 202, json: { workflow_id: id, workflow } });
  });
  await page.route(`**/api/workflows/${id}/cancel`, route => {
    workflow = { ...workflow, status: 'cancelled', cancel_requested: true };
    return route.fulfill({ json: workflow });
  });
  await page.reload();
  await page.getByRole('button', { name: en.LibraryManagement.constellation.retryWorkflow, exact: true }).click();
  await expect(page.getByText('E2E retry failed', { exact: true })).toBeVisible();
  retryFails = false;
  await page.getByRole('button', { name: en.LibraryManagement.constellation.retryWorkflow, exact: true }).click();
  await page.getByRole('button', { name: en.LibraryManagement.constellation.cancelWorkflow, exact: true }).click();
  await expect(page.getByRole('button', { name: en.LibraryManagement.constellation.retryWorkflow, exact: true })).toBeVisible();
});
