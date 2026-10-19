import { test, expect, type APIRequestContext, type Page } from '@playwright/test';
import path from 'node:path';

const backend = process.env.E2E_BACKEND!;
const copy = {
  en: { title: 'EXPLORE', find: 'Find a fact', finder: 'Fact Finder', search: 'Search Genre',
    journey: 'Current journey', where: 'Show films where', clear: 'Clear all',
    removed: ['Local factual exploration', 'Rediscover your collection through Genre, People, Countries, and Decades.', 'Accepted facts only'] },
  zh: { title: '探索', find: '查找事实', finder: '事实查找器', search: '搜索类型',
    journey: '当前探索路径', where: '显示符合以下事实的影片', clear: '清除全部',
    removed: ['本地事实探索', '沿着类型、人物、国家与年代，重新发现你的收藏。', '仅使用已接受事实'] },
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
  for (const width of [1920, 390, 320]) {
    test(`${locale} Explore keeps a clean header and accessible local filtering at ${width}px`, async ({ page, request }) => {
      const text = copy[locale];
      const askRequests: string[] = [];
      page.on('request', request => {
        if (request.method() === 'POST' && new URL(request.url()).pathname.startsWith('/api/ask')) askRequests.push(request.url());
      });
      await page.setViewportSize({ width, height: width === 1920 ? 1080 : 844 });
      await page.goto(`/${locale}/explore`);
      const header = page.locator('header').filter({ has: page.getByRole('heading', { name: text.title, exact: true }) });
      await expect(header.getByRole('heading', { level: 1 })).toBeVisible();
      // No dynamic collection count or header helper copy remains, regardless of its value.
      await expect(header.locator('p, span')).toHaveCount(0);
      expect(await header.innerText()).not.toMatch(/\d/);
      for (const removed of text.removed) await expect(page.getByText(removed, { exact: true })).toHaveCount(0);
      await expect(page.locator('section[aria-labelledby="lens-deck-title"] button')).toHaveCount(4);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      if (width !== 320) await capture(page, `explore-ui-${locale}-${width}.png`);

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
