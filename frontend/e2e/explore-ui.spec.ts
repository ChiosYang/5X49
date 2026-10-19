import { test, expect, type APIRequestContext, type Page } from '@playwright/test';
import path from 'node:path';
import type { ExploreContext } from '../src/types/movie';

const backend = process.env.E2E_BACKEND!;
const copy = {
  en: { title: 'EXPLORE', find: 'Find a fact', finder: 'Fact Finder', search: 'Search Genre',
    journey: 'Current journey', where: 'Show films where', clear: 'Clear all',
    removed: ['Local factual exploration', 'Rediscover your collection through Genre, People, Countries, and Decades.', 'Accepted facts only', 'Data confidence'] },
  zh: { title: '探索', find: '查找事实', finder: '事实查找器', search: '搜索类型',
    journey: '当前探索路径', where: '显示符合以下事实的影片', clear: '清除全部',
    removed: ['本地事实探索', '沿着类型、人物、国家与年代，重新发现你的收藏。', '仅使用已接受事实', '数据可信度'] },
};

async function read(request: APIRequestContext, url: string) {
  const response = await request.get(`${backend}${url}`);
  expect(response.ok()).toBeTruthy();
  return response.json();
}

async function cleanup(request: APIRequestContext) {
  expect((await request.post(`${backend}/__e2e/control`, {
    headers: { 'x-e2e-token': process.env.E2E_TOKEN! }, data: { action: 'identity_cleanup' },
  })).ok()).toBeTruthy();
}

async function capture(page: Page, name: string) {
  await page.evaluate(async () => {
    await document.fonts.ready;
    const visibleImages = [...document.images].filter(image => {
      const bounds = image.getBoundingClientRect();
      return bounds.bottom > 0 && bounds.top < innerHeight && bounds.right > 0 && bounds.left < innerWidth;
    });
    await Promise.all(visibleImages.map(image => image.decode().catch(() => {})));
    // Refresh Chrome's composited frame after local artwork finishes decoding.
    const root = document.documentElement;
    const opacity = root.style.opacity;
    const frame = () => new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
    root.style.opacity = '0';
    await frame(); await frame();
    root.style.opacity = opacity;
    await frame(); await frame();
  });
  await page.screenshot({ path: path.join('e2e-artifacts', name), animations: 'disabled' });
}

async function titleMetrics(page: Page) {
  await page.evaluate(() => document.fonts.ready);
  return page.locator('h1').evaluate(heading => {
    const style = getComputedStyle(heading);
    const bounds = heading.getBoundingClientRect();
    const header = getComputedStyle(heading.closest('header')!);
    return {
      font: style.fontFamily, size: style.fontSize, weight: style.fontWeight,
      lineHeight: style.lineHeight, spacing: style.letterSpacing,
      x: bounds.x, y: bounds.y,
      direction: header.flexDirection, gap: header.gap, paddingBottom: header.paddingBottom,
    };
  });
}

test.beforeAll(async ({ request }) => {
  await cleanup(request);
  const media = path.join(process.env.E2E_ROOT!, 'normal/media');
  const saved = await request.put(`${backend}/settings/media-dir?media_dir=${encodeURIComponent(media)}`);
  expect(saved.ok()).toBeTruthy();
  // The backend canonicalizes Windows short temp paths when saving the root.
  const { media_dir: canonicalMedia } = await saved.json();
  const scan = await request.post(`${backend}/library/scan?media_dir=${encodeURIComponent(canonicalMedia)}`);
  expect(scan.ok()).toBeTruthy();
  const { workflow_id } = await scan.json();
  await expect.poll(async () => (await read(request, `/workflows/${workflow_id}`)).status, { timeout: 45000 }).toBe('succeeded');
});

test.afterAll(async ({ request }) => { await cleanup(request); });

test.beforeEach(async ({ context }) => {
  await context.route('**/*', route => ['127.0.0.1', 'localhost'].includes(new URL(route.request().url()).hostname)
    ? route.continue() : route.abort('blockedbyclient'));
});

for (const locale of ['en', 'zh'] as const) {
  for (const width of [1920, 1024, 768, 390, 320]) {
    test(`${locale} Explore keeps a clean header and accessible local filtering at ${width}px`, async ({ page, request }) => {
      const text = copy[locale];
      const askRequests: string[] = [];
      page.on('request', request => {
        if (request.method() === 'POST' && new URL(request.url()).pathname.startsWith('/api/ask')) askRequests.push(request.url());
      });
      await page.setViewportSize({ width, height: width === 1920 ? 1080 : 844 });
      await page.goto(`/${locale}/library`);
      const libraryTitle = await titleMetrics(page);
      await page.goto(`/${locale}/explore`);
      const header = page.locator('header').filter({ has: page.getByRole('heading', { name: text.title, exact: true }) });
      await expect(header.getByRole('heading', { level: 1 })).toBeVisible();
      await expect(header.locator('h1')).toHaveClass('type-display-editorial');
      expect(await titleMetrics(page)).toEqual(libraryTitle);
      await expect(page.locator('nav.fixed').first()).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)');
      // No dynamic collection count or header helper copy remains, regardless of its value.
      await expect(header.locator('p, span')).toHaveCount(0);
      expect(await header.innerText()).not.toMatch(/\d/);
      for (const removed of text.removed) await expect(page.getByText(removed, { exact: true })).toHaveCount(0);
      const deck = page.locator('section[aria-labelledby="lens-deck-title"]');
      const cards = deck.getByRole('button');
      await expect(cards).toHaveCount(4);
      await expect(cards.locator('svg')).toHaveCount(0);
      await expect(deck.locator('details')).toHaveCount(0);
      await expect(deck).toHaveCSS('border-bottom-width', '0px');
      await expect(deck).toHaveCSS('border-top-width', '0px');
      const overview = await read(request, '/explore');
      for (const [index, dimension] of overview.dimensions.entries()) {
        const card = cards.nth(index);
        await expect(card).toHaveCSS('border-width', '1px');
        const ratio = card.locator('span[aria-label]');
        await expect(ratio).toHaveText(`${dimension.coverage.covered_films}/${dimension.coverage.total_films}`);
        await expect(ratio).toHaveAttribute('aria-label', /\S/);
      }
      // Country display names switch from stable server keys after hydration.
      // Wait for that visible state before capturing or clicking client controls.
      const context: ExploreContext = await read(request, '/explore/context?limit=6');
      const country = context.dimensions.find(dimension => dimension.dimension === 'country')!.items[0];
      const countryName = new Intl.DisplayNames([locale], { type: 'region' }).of(country.key)!;
      await expect(cards.nth(2).locator('p[title]')).toHaveText(countryName);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      if (width === 1920 || width === 390) await capture(page, `explore-cards-${locale}-${width}.png`);

      const initialUrl = page.url();
      const find = header.getByRole('button', { name: text.find, exact: true });
      await find.click();
      const dialog = page.getByRole('dialog', { name: text.finder, exact: true });
      await expect(dialog).toBeVisible();
      const input = dialog.getByRole('textbox', { name: text.search, exact: true });
      await expect(input).toBeFocused();
      expect(page.url()).toBe(initialUrl);
      const facets = await read(request, '/explore/facets/genre?limit=30');
      const fact = facets.items[0];
      expect(fact).toBeTruthy();
      const searched = page.waitForResponse(response => {
        const url = new URL(response.url());
        return url.pathname === '/api/explore/facets/genre' && url.searchParams.get('q') === fact.label && response.ok();
      });
      await input.fill(fact.label);
      await searched;
      await input.press('Enter');
      await expect(dialog).toBeVisible();
      expect(page.url()).toBe(initialUrl);
      await dialog.getByRole('button').filter({ has: page.getByText(fact.label, { exact: true }) }).click();
      await expect(dialog).toBeHidden();
      await expect.poll(() => new URL(page.url()).searchParams.get('genre')).toBe(fact.key);
      const journey = page.getByRole('region', { name: text.journey, exact: true });
      await expect(journey).toBeVisible();
      await expect(journey.getByText(text.where, { exact: true })).toBeVisible();
      const label = journey.locator('#query-ribbon-title');
      await expect(label).toHaveClass('sr-only');
      const bounds = await label.boundingBox();
      expect(bounds?.width).toBe(1); expect(bounds?.height).toBe(1);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await journey.getByRole('button', { name: text.clear, exact: true }).click();
      await expect.poll(() => new URL(page.url()).search).toBe('');
      await expect(journey).toHaveCount(0);
      await find.click();
      await expect(dialog).toBeVisible();
      await page.keyboard.press('Escape');
      await expect(find).toBeFocused();
      expect(askRequests).toEqual([]);
    });
  }
}

test('empty Explore keeps live 0/0 coverage and usable lens entries', async ({ page }) => {
  await cleanup(page.request);
  await page.goto('/en/explore');
  const cards = page.locator('section[aria-labelledby="lens-deck-title"] button');
  await expect(cards).toHaveCount(4);
  for (const card of await cards.all()) await expect(card.locator('span[aria-label]')).toHaveText('0/0');
  await cards.first().click();
  await expect(page.getByRole('dialog')).toBeVisible();
});
