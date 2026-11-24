import { test, expect, type APIRequestContext, type Page } from '@playwright/test';
import path from 'node:path';
import en from '../messages/en.json';
import zh from '../messages/zh.json';

const backend = process.env.E2E_BACKEND!;
async function control(request: APIRequestContext, action: string) {
  const response = await request.post(`${backend}/__e2e/control`, {
    headers: { 'x-e2e-token': process.env.E2E_TOKEN! }, data: { action },
  });
  expect(response.ok()).toBeTruthy();
}
async function capture(page: Page, name: string) {
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: path.join('e2e-artifacts', `menus-${name}.png`), animations: 'disabled' });
}

test.beforeAll(async ({ request }) => {
  await control(request, 'identity_cleanup');
  await control(request, 'identity_fixtures');
});
test.afterAll(async ({ request }) => { await control(request, 'identity_cleanup'); });
test.beforeEach(async ({ context }) => {
  await context.route('**/*', route => ['127.0.0.1', 'localhost'].includes(new URL(route.request().url()).hostname)
    ? route.continue() : route.abort('blockedbyclient'));
});

for (const locale of ['en', 'zh'] as const) {
  for (const width of [1440, 390, 320]) {
    test(`${locale} Library omits More, Settings maintenance owns identity review and sidebar omits Search at ${width}px`, async ({ page, request }) => {
      const copy = locale === 'en' ? en : zh;
      const writes: string[] = [];
      page.on('request', req => { if (req.method() !== 'GET' && req.url().includes('/api/')) writes.push(req.url()); });
      await page.setViewportSize({ width, height: 900 });
      await page.goto(`/${locale}/library?q=Identity&sort=duration&dir=desc`);
      const nav = page.locator('nav.navigation-bar');
      await expect(page.getByRole('button', { name: copy.LibraryCare.more, exact: true })).toHaveCount(0);
      await expect(page.getByRole('link', { name: copy.LibraryCare.identityReview, exact: true })).toHaveCount(0);
      await capture(page, `header-${locale}-${width}`);

      const sidebarTrigger = nav.getByRole('button', { name: copy.Navigation.menu, exact: true });
      await sidebarTrigger.click();
      const sidebar = page.getByRole('dialog', { name: copy.Navigation.menu, exact: true });
      await expect(sidebar.getByRole('button', { name: copy.Navigation.search, exact: true })).toHaveCount(0);
      await expect(sidebar.getByRole('link', { name: copy.Navigation.search, exact: true })).toHaveCount(0);
      await capture(page, `sidebar-${locale}-${width}`);
      await page.keyboard.press('Escape');
      await expect(sidebarTrigger).toBeFocused();
      await sidebarTrigger.click();
      await sidebar.getByRole('link', { name: copy.Navigation.explore, exact: true }).click();
      await expect(page).toHaveURL(/\/explore$/);
      await expect(sidebar).toHaveCount(0);
      await nav.getByRole('button', { name: copy.Navigation.search, exact: true }).click();
      const search = nav.getByRole('searchbox', { name: copy.LibrarySearch.query, exact: true });
      await expect(search).toBeFocused();
      await search.fill('Identity');
      await search.press('Enter');
      await expect.poll(() => new URL(page.url()).searchParams.get('q')).toBe('Identity');
      await expect(page.locator('.library-card-media')).toHaveCount(2);

      await page.goto(`/${locale}/settings?section=library-maintenance`);
      const maintenanceUrl = page.url();
      const identity = page.getByRole('link', { name: copy.IdentityReview.title, exact: true });
      const { total } = await (await request.get(`${backend}/library/identity-reviews`)).json();
      await expect(identity).toBeVisible();
      await expect(identity).toHaveAccessibleDescription(new RegExp(String(total)));
      await expect(identity).toHaveAttribute('href', `/${locale}/library/identity-review`);
      await capture(page, `maintenance-identity-${locale}-${width}`);
      await identity.click();
      await expect(page.getByRole('heading', { name: copy.IdentityReview.title, exact: true })).toBeVisible();
      await expect(page.locator('html')).toHaveAttribute('lang', locale);
      await page.goBack();
      await expect(page).toHaveURL(maintenanceUrl);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      expect(writes).toEqual([]);
    });
  }

  test(`${locale} empty-library omits More and Settings maintenance exposes identity review with a truthful zero`, async ({ page, request }) => {
    const copy = locale === 'en' ? en : zh;
    await control(request, 'identity_cleanup');
    try {
      await page.goto(`/${locale}/library`);
      await expect(page.getByRole('button', { name: copy.Onboarding.scanNow, exact: true })).toBeVisible();
      await expect(page.getByRole('button', { name: copy.LibraryCare.scanNow, exact: true })).toHaveCount(0);
      await expect(page.getByRole('button', { name: copy.LibraryCare.more, exact: true })).toHaveCount(0);

      await page.goto(`/${locale}/settings?section=library-maintenance`);
      const identity = page.getByRole('link', { name: copy.IdentityReview.title, exact: true });
      await expect(identity).toHaveAccessibleDescription(/0/);
      await identity.click();
      await expect(page.getByRole('heading', { name: copy.IdentityReview.title, exact: true })).toBeVisible();
      await expect(page.getByText(copy.IdentityReview.empty, { exact: true })).toBeVisible();
    } finally { await control(request, 'identity_fixtures'); }
  });
}
