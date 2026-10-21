import { test, expect, type APIRequestContext, type Page } from '@playwright/test';
import path from 'node:path';
import en from '../messages/en.json';
import zh from '../messages/zh.json';

const backend = process.env.E2E_BACKEND!;
async function control(request: APIRequestContext, action: string, extra = {}) {
  const response = await request.post(`${backend}/__e2e/control`, {
    headers: { 'x-e2e-token': process.env.E2E_TOKEN! }, data: { action, ...extra },
  });
  expect(response.ok()).toBeTruthy();
  return response.json();
}
async function capture(page: Page, name: string) {
  await page.evaluate(async () => {
    await document.fonts.ready;
    const visibleImages = [...document.images].filter(image => {
      const bounds = image.getBoundingClientRect();
      return bounds.bottom > 0 && bounds.top < innerHeight;
    });
    await Promise.all(visibleImages.map(image => image.decode().catch(() => {})));
  });
  await page.screenshot({ path: path.join('e2e-artifacts', `copy-${name}.png`), fullPage: true, animations: 'disabled' });
}

test.beforeAll(async ({ request }) => {
  await control(request, 'identity_cleanup');
  await control(request, 'library_filter_fixture');
});
test.afterAll(async ({ request }) => { await control(request, 'identity_cleanup'); });
test.beforeEach(async ({ context }) => {
  await context.route('**/*', route => ['127.0.0.1', 'localhost'].includes(new URL(route.request().url()).hostname)
    ? route.continue() : route.abort('blockedbyclient'));
});

for (const locale of ['en', 'zh'] as const) {
  for (const width of [1440, 390]) {
    test(`${locale} complete route copy and layout audit at ${width}px`, async ({ page, request }) => {
      test.setTimeout(240000);
      const copy = locale === 'en' ? en : zh;
      const ai: string[] = [];
      const errors: string[] = [];
      page.on('pageerror', error => errors.push(error.message));
      page.on('request', req => { if (req.method() === 'POST' && /\/api\/(ask\/interpret|films\/[^/]+\/analysis)/.test(req.url())) ai.push(req.url()); });
      await page.setViewportSize({ width, height: 900 });
      const films = await (await request.get(`${backend}/library/films`)).json();
      const routes: Array<[string, string[]]> = [
        ['/library', []],
        ['/library?q=Orbit', []],
        ['/library?q=tape', []],
        ['/library?view=metadata', []],
        ['/library?view=inbox', []],
        ['/library?view=offline', []],
        ['/explore', []],
        ['/explore/collections', []],
        ['/explore/search', []],
        ['/explore/filter', []],
        ['/diary', [copy.Diary.eyebrow, copy.Diary.subtitle]],
        ['/diary?view=recent', [copy.Diary.eyebrow, copy.Diary.subtitle]],
        ['/diary?view=dna', [copy.CinemaDna.eyebrow, copy.CinemaDna.intro]],
        [`/library/${films[0].id}`, [copy.Diary.filmSectionEyebrow, copy.Genealogy.subtitle]],
        ['/library/identity-review', []],
        ['/library/activity', [copy.Activity.eyebrow]],
        ['/library/manage', [copy.LibraryManagement.constellation.eyebrow, copy.LibraryManagement.constellation.subtitle, copy.LibraryManagement.constellation.liveTopology]],
        ['/library/manage/concepts', ['5X49 · Management interaction study']],
        ['/library/manage/visual-concepts', ['Visual interaction lab', '5X49 · Visual interaction study']],
        ['/settings', [copy.Settings.subtitle, copy.Settings.generalEyebrow, copy.Settings.generalDesc, copy.Settings.languageDesc]],
        // "Service connections" is now the actual category label, rather than an eyebrow.
        ['/settings?section=integrations', [copy.Settings.integrationsDesc, copy.Settings.aiProviderDesc, copy.Settings.modelDesc, copy.Settings.apiDesc]],
        ['/settings?section=library', [copy.Settings.libraryEyebrow, copy.Settings.librarySettingsDesc, copy.Settings.metadataPreferencesDesc, copy.Settings.automationDesc]],
        ['/settings?section=maintenance', []],
        ['/admin/health', []],
        ['/ask', [copy.Ask.eyebrow, copy.Ask.description]],
      ];
      for (const [index, [route, removed]] of routes.entries()) {
        await test.step(route, async () => {
          await page.goto(`/${locale}${route}`);
          await expect(page.locator('html')).toHaveAttribute('lang', locale);
          await expect(page.locator('h1')).toHaveCount(1);
          await expect(page.locator('h1')).toBeVisible();
          await expect(page.getByRole('heading', { name: copy.Errors.title, exact: true })).toHaveCount(0);
          for (const text of removed) await expect(page.getByText(text, { exact: true })).toHaveCount(0);
          if (route.startsWith('/library?q=')) {
            await expect(page.getByRole('status').filter({ hasText: route.includes('Orbit') ? 'Orbit' : 'tape' })).toHaveCount(0);
          }
          if (route === '/library?q=tape') {
            await expect(page.getByText(copy.LibrarySearch.empty.replace('{query}', 'tape'), { exact: true })).toBeVisible();
          }
          if (route === '/ask') {
            await expect(page).toHaveURL(/\/explore$/);
            await expect(page.getByRole('searchbox', { name: copy.Discovery.label, exact: true })).toBeVisible();
            await expect(page.locator('#ask-form')).toHaveCount(0);
          }
          if (route === `/library/${films[0].id}`) {
            await expect(page.locator('h1').locator('..').locator('p')).toHaveCount(0);
          }
          // All real routes, including the existing concept studies, must fit the viewport.
          expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
          await expect(page.locator('nav.navigation-bar')).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)');
          await capture(page, `${locale}-${width}-${index}-${route.split('?')[0].replaceAll('/', '-')}`);
        });
      }
      expect(ai).toEqual([]);
      expect(errors).toEqual([]);
    });
  }

  test(`${locale} empty library, no-result and failed reads retain recovery`, async ({ page, request }) => {
    const copy = locale === 'en' ? en : zh;
    await control(request, 'identity_cleanup');
    try {
      await page.setViewportSize({ width: 320, height: 844 });
      await page.goto(`/${locale}/library`);
      await expect(page.getByRole('button', { name: copy.Onboarding.scanNow, exact: true })).toBeVisible();
      await capture(page, `${locale}-empty-library-320`);
      await page.goto(`/${locale}/library?q=tape`);
      await expect(page.getByText(copy.LibrarySearch.empty.replace('{query}', 'tape'), { exact: true })).toBeVisible();
      await expect(page.getByRole('link', { name: copy.Library.resetFilter, exact: true })).toBeVisible();
      await expect(page.getByRole('status').filter({ hasText: 'tape' })).toHaveCount(0);
      await capture(page, `${locale}-empty-search-320`);
      await control(request, 'search_failure', { enabled: true });
      await page.reload();
      await expect(page.getByRole('heading', { name: copy.Errors.title, exact: true })).toBeVisible();
      await expect(page.getByText(copy.Errors.description, { exact: true })).toBeVisible();
      await expect(page.getByText(copy.Errors.eyebrow, { exact: true })).toHaveCount(0);
      await capture(page, `${locale}-error-320`);
      await control(request, 'search_failure', { enabled: false });
      await page.getByRole('button', { name: copy.Errors.retry, exact: true }).click();
      await expect(page.getByText(copy.LibrarySearch.empty.replace('{query}', 'tape'), { exact: true })).toBeVisible();
    } finally {
      await control(request, 'search_failure', { enabled: false });
      await control(request, 'library_filter_fixture');
    }
  });
}

test('a distinct original film title remains visible', async ({ page, request }) => {
  const { film_id: filmId } = await control(request, 'manual_metadata_fixture');
  await page.goto(`/en/library/${filmId}`);
  await expect(page.locator('h1')).toHaveText('Source Film');
  await expect(page.locator('h1').locator('..').locator('p')).toHaveText('Source Original');
  await capture(page, 'distinct-original-title');
});
