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
    test(`${locale} More owns identity review and sidebar omits Search at ${width}px`, async ({ page, request }) => {
      const copy = locale === 'en' ? en : zh;
      const writes: string[] = [];
      page.on('request', req => { if (req.method() !== 'GET' && req.url().includes('/api/')) writes.push(req.url()); });
      await page.setViewportSize({ width, height: 900 });
      await page.goto(`/${locale}/library?q=Identity&sort=duration&dir=desc`);
      const original = page.url();
      const nav = page.locator('nav.navigation-bar');
      const more = page.getByRole('button', { name: copy.LibraryCare.more, exact: true });
      const menu = page.getByRole('menu', { name: copy.LibraryCare.more, exact: true });
      const identity = menu.getByRole('menuitem', { name: copy.LibraryCare.identityReview, exact: true });
      await expect(page.getByRole('link', { name: copy.LibraryCare.identityReview, exact: true })).toHaveCount(0);
      await capture(page, `header-${locale}-${width}`);
      await more.click();
      await expect(menu).toBeVisible();
      const { total } = await (await request.get(`${backend}/library/identity-reviews`)).json();
      await expect(identity).toHaveAccessibleDescription(new RegExp(String(total)));
      await expect(identity).toContainText(String(total));
      await expect(identity).toHaveAttribute('href', `/${locale}/library/identity-review`);
      await capture(page, `more-${locale}-${width}`);
      expect(await menu.evaluate(element => element.getBoundingClientRect().left >= 0 && element.getBoundingClientRect().right <= innerWidth)).toBe(true);
      await page.keyboard.press('Escape');
      await expect(menu).toHaveCount(0);
      await expect(more).toBeFocused();

      await more.press('ArrowDown');
      await expect(identity).toBeFocused();
      await identity.press('End');
      await expect(menu.getByRole('menuitem', { name: copy.LibraryCare.librarySettings, exact: true })).toBeFocused();
      await page.keyboard.press('ArrowDown');
      await expect(identity).toBeFocused();
      await page.keyboard.press('ArrowUp');
      await page.keyboard.press('Tab');
      await expect(menu).toHaveCount(0); // Tab exits instead of trapping focus.
      await more.focus();
      await more.press('Enter');
      await expect(identity).toBeFocused();
      await identity.press('Enter');
      await expect(page.getByRole('heading', { name: copy.IdentityReview.title, exact: true })).toBeVisible();
      await expect(page.locator('html')).toHaveAttribute('lang', locale);
      await page.goBack();
      await expect(page).toHaveURL(original);
      await expect(more).toHaveAttribute('aria-expanded', 'false');
      await more.click();
      await page.locator('h1').click();
      await expect(menu).toHaveCount(0);

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
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      expect(writes).toEqual([]);
    });
  }

  test(`${locale} empty-library More still exposes identity review with a truthful zero`, async ({ page, request }) => {
    const copy = locale === 'en' ? en : zh;
    await control(request, 'identity_cleanup');
    try {
      await page.goto(`/${locale}/library`);
      await expect(page.getByRole('button', { name: copy.Onboarding.scanNow, exact: true })).toBeVisible();
      await expect(page.getByRole('button', { name: copy.LibraryCare.scanNow, exact: true })).toHaveCount(0);
      await page.getByRole('button', { name: copy.LibraryCare.more, exact: true }).click();
      const identity = page.getByRole('menuitem', { name: copy.LibraryCare.identityReview, exact: true });
      await expect(identity).toHaveAccessibleDescription(/0/);
      await identity.click();
      await expect(page.getByRole('heading', { name: copy.IdentityReview.title, exact: true })).toBeVisible();
      await expect(page.getByText(copy.IdentityReview.empty, { exact: true })).toBeVisible();
    } finally { await control(request, 'identity_fixtures'); }
  });
}
