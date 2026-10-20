import { test, expect, type APIRequestContext, type Page } from '@playwright/test';
import path from 'node:path';
import { copyFile } from 'node:fs/promises';
import en from '../messages/en.json';
import zh from '../messages/zh.json';

const backend = process.env.E2E_BACKEND!;
const nav = (page: Page) => page.locator('nav.navigation-bar');
const cards = (page: Page) => page.locator('.library-card-media');
async function control(request: APIRequestContext, action: string, extra = {}) {
  const response = await request.post(`${backend}/__e2e/control`, {
    headers: { 'x-e2e-token': process.env.E2E_TOKEN! }, data: { action, ...extra },
  });
  expect(response.ok()).toBeTruthy();
}
async function capture(page: Page, name: string) {
  await page.evaluate(async () => {
    await document.fonts.ready;
    await Promise.all([...document.images].map(image => image.decode().catch(() => {})));
  });
  await page.screenshot({ path: path.join('e2e-artifacts', `search-${name}.png`), animations: 'disabled' });
}
async function open(page: Page, locale: 'en' | 'zh' = 'en') {
  const copy = locale === 'en' ? en : zh;
  await nav(page).getByRole('button', { name: copy.Navigation.search, exact: true }).click();
  const input = nav(page).getByRole('searchbox', { name: copy.LibrarySearch.query, exact: true });
  await expect(input).toBeFocused();
  return input;
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
  for (const width of [1920, 1024, 768, 390, 320]) {
    test(`${locale} navigation search expands, closes and searches the whole library at ${width}px`, async ({ page }) => {
      const copy = locale === 'en' ? en : zh;
      const aiRequests: string[] = [];
      page.on('request', request => {
        if (request.method() === 'POST' && /\/api\/(ask|analysis)/.test(request.url())) aiRequests.push(request.url());
      });
      await page.setViewportSize({ width, height: width === 1920 ? 1080 : 844 });
      await page.goto(`/${locale}/library?view=metadata&q=old&filter=watched&favorite=true&year_min=2000&page=2`);
      const before = page.url();
      const logo = nav(page).getByRole('link', { name: '5X49', exact: true });
      const logoBefore = await logo.boundingBox();
      const input = await open(page, locale);
      await input.fill('Orbit');
      expect(page.url()).toBe(before);
      await expect(nav(page)).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)');
      if (width >= 1024) {
        await expect(logo).toBeVisible();
        expect(await logo.boundingBox()).toEqual(logoBefore);
        const form = (await nav(page).getByRole('search').boundingBox())!;
        expect(form.x).toBeGreaterThan(logoBefore!.x + logoBefore!.width);
        const status = (await nav(page).locator('.navigation-status').boundingBox())!;
        expect(form.x + form.width).toBeLessThanOrEqual(status.x);
      } else {
        await expect(logo).toBeHidden();
        await expect(nav(page).getByRole('button', { name: copy.Navigation.menu, exact: true })).toBeHidden();
      }
      await input.press('Escape');
      const trigger = nav(page).getByRole('button', { name: copy.Navigation.search, exact: true });
      await expect(trigger).toBeFocused();
      expect(page.url()).toBe(before);
      await trigger.click();
      await expect(input).toHaveValue('old'); // Discard a cancelled draft.
      await input.fill('Orbit');
      if (width === 1920 || width === 390) await capture(page, `open-${locale}-${width}`);
      await input.press('Enter');
      await expect.poll(() => new URL(page.url()).search).toBe('?q=Orbit');
      await expect(page.locator('html')).toHaveAttribute('lang', locale);
      await expect(cards(page)).toHaveCount(5);
      await expect(page.getByRole('status').filter({ hasText: '5' }).first()).toBeVisible();
      await expect(page.getByRole('status').filter({ hasText: 'Orbit' })).toHaveCount(0);
      if (width === 1920 || width === 390) await capture(page, `results-${locale}-${width}`);
      const again = await open(page, locale);
      await expect(again).toHaveValue('Orbit');
      await again.press('Enter'); // Identical repeated submissions remain usable.
      await expect(nav(page).getByRole('search')).toHaveCount(0);
      await expect(cards(page)).toHaveCount(5);
      await expect(await open(page, locale)).toHaveValue('Orbit');
      await nav(page).getByRole('button', { name: copy.LibrarySearch.close, exact: true }).click();
      await expect(trigger).toBeFocused();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      expect(aiRequests).toEqual([]);
    });
  }
}

test('sidebar omits Search; navigation search, history, pagination and filters keep committed keywords', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/en/explore');
  await nav(page).getByRole('button', { name: 'Menu', exact: true }).click();
  const menu = page.getByRole('dialog', { name: 'Menu', exact: true });
  await expect(menu.getByRole('button', { name: 'Search', exact: true })).toHaveCount(0);
  await expect(menu.getByRole('link', { name: 'Search', exact: true })).toHaveCount(0);
  await page.keyboard.press('Escape');
  const input = await open(page);
  await expect(input).toBeFocused();
  await input.fill('Shelf');
  await input.press('Enter');
  await expect(cards(page)).toHaveCount(40);
  await page.getByRole('link', { name: 'Next page', exact: true }).click();
  await expect(cards(page)).toHaveCount(2);
  const paged = page.url();
  expect(new URL(paged).searchParams.get('q')).toBe('Shelf');
  await page.getByRole('button', { name: 'Filter', exact: true }).click();
  await expect(page.getByRole('dialog').getByRole('searchbox')).toHaveValue('Shelf');
  await page.keyboard.press('Escape');
  await (await open(page)).fill('Orbit');
  await input.press('Enter');
  await expect(cards(page)).toHaveCount(5);
  await page.goBack();
  await expect(page).toHaveURL(paged);
  await expect(cards(page)).toHaveCount(2);
  await expect(await open(page)).toHaveValue('Shelf');
  await page.goForward(); // Navigation discards the unsubmitted search state.
  await expect(cards(page)).toHaveCount(5);
  await expect(await open(page)).toHaveValue('Orbit');
});

test('IME composition never submits or closes while candidates are being chosen', async ({ page }) => {
  await page.goto('/zh/library');
  const before = page.url();
  const input = await open(page, 'zh');
  await input.fill('电影');
  await input.dispatchEvent('compositionstart');
  await input.press('Enter');
  await input.press('Escape');
  expect(page.url()).toBe(before);
  await expect(input).toBeFocused();
  await expect(input).toHaveValue('电影');
  await input.dispatchEvent('compositionend');
  // Legacy WebKit IME confirmation reports keyCode=229 after compositionend.
  await input.dispatchEvent('keydown', { key: 'Enter', keyCode: 229 });
  expect(page.url()).toBe(before);
  await input.press('Enter');
  await expect.poll(() => new URL(page.url()).searchParams.get('q')).toBe('电影');
});

test('long and blank input, empty results and reduced motion stay usable on mobile', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 844 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/en/library');
  const input = await open(page);
  expect(await nav(page).locator('.navigation-search').evaluate(element => parseFloat(getComputedStyle(element).transitionDuration))).toBeLessThanOrEqual(0.001);
  const long = '无匹配abc&<'.repeat(30);
  await input.fill(long);
  await expect(input).toHaveValue(long.slice(0, 200));
  await input.press('Enter');
  await expect.poll(() => new URL(page.url()).searchParams.get('q')).toBe(long.slice(0, 200));
  await expect(cards(page)).toHaveCount(0);
  await expect(page.getByRole('status').filter({ hasText: '0 films' })).toBeVisible();
  await expect(page.getByText(/films? matching/)).toHaveCount(0);
  await expect(page.getByText(en.LibrarySearch.empty.replace('{query}', long.slice(0, 200)), { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await capture(page, 'empty-long-mobile');
  const again = await open(page);
  await again.fill('   ');
  await again.press('Enter');
  await expect.poll(() => new URL(page.url()).search).toBe('');
  await expect(cards(page)).toHaveCount(40);
});

test('legacy search links preserve locale and explicit page and ignore unsafe extra parameters', async ({ page }) => {
  for (const prefix of ['/en', '/zh', '']) {
    const query = 'Shelf';
    await page.goto(`${prefix}/search?q=${query}&page=2&view=offline&favorite=true&redirect=https://example.com`);
    await expect.poll(() => new URL(page.url()).pathname).toBe(prefix === '/en' ? '/en/library' : '/library');
    await expect.poll(() => new URL(page.url()).search).toBe('?q=Shelf&page=2');
    await expect(cards(page)).toHaveCount(2);
    await expect(page.locator('html')).toHaveAttribute('lang', prefix === '/en' ? 'en' : 'zh');
  }
  await page.goto('/en/search?q=%20%20&page=99');
  await expect(page).toHaveURL(/\/en\/library$/);
  await page.goto('/en/search?q=Shelf&page=9');
  await expect.poll(() => new URL(page.url()).searchParams.get('page')).toBe('2');
  await expect(cards(page)).toHaveCount(2);
  await expect(page.getByText(en.LibrarySearch.empty.replace('{query}', 'Shelf'), { exact: true })).toHaveCount(0);
});

test('failed search reads show an error and allow retry and another navigation search', async ({ page, request }) => {
  await page.goto('/en/library');
  await control(request, 'search_failure', { enabled: true });
  try {
    const input = await open(page);
    await input.fill('Orbit');
    await input.press('Enter');
    await expect(page.getByRole('heading', { name: en.Errors.title, exact: true })).toBeVisible();
    await expect(page.getByRole('status').filter({ hasText: 'matching' })).toHaveCount(0);
    await capture(page, 'error-desktop');
  } finally { await control(request, 'search_failure', { enabled: false }); }
  await page.getByRole('button', { name: en.Errors.retry, exact: true }).click();
  await expect(cards(page)).toHaveCount(5);
  await (await open(page)).fill('Shelf');
  await nav(page).getByRole('searchbox').press('Enter');
  await expect(cards(page)).toHaveCount(40);
});

test.describe('animation recording', () => {
  test('desktop expand and collapse', async ({ browser }) => {
    const context = await browser.newContext({ baseURL: process.env.E2E_BASE_URL,
      viewport: { width: 1440, height: 900 }, hasTouch: false,
      recordVideo: { dir: 'e2e-artifacts/search-video', size: { width: 1440, height: 900 } } });
    await context.route('**/*', route => ['127.0.0.1', 'localhost'].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort('blockedbyclient'));
    const page = await context.newPage();
    try {
      await page.goto('/en/library?q=Orbit');
      await expect(cards(page)).toHaveCount(5);
      await page.waitForTimeout(400);
      const input = await open(page);
      await input.fill('Orbit');
      await page.waitForTimeout(600);
      await input.press('Escape');
      await page.waitForTimeout(600);
      await open(page);
      await page.waitForTimeout(600);
      await nav(page).getByRole('button', { name: 'Close search', exact: true }).click();
      await page.waitForTimeout(400);
    } finally { await context.close(); }
    await copyFile(await page.video()!.path(), 'e2e-artifacts/search-expand-collapse.webm');
  });
});
