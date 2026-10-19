import { test, expect, type APIRequestContext } from '@playwright/test';
import path from 'node:path';

const backend = process.env.E2E_BACKEND!;
let films: Array<{ id: string; title: string }>;
async function read(request: APIRequestContext, url: string) {
  const response = await request.get(`${backend}${url}`);
  expect(response.ok()).toBeTruthy(); return response.json();
}
async function cleanup(request: APIRequestContext) {
  expect((await request.post(`${backend}/__e2e/control`, {
    headers: { 'x-e2e-token': process.env.E2E_TOKEN! }, data: { action: 'identity_cleanup' },
  })).ok()).toBeTruthy();
}

test.beforeAll(async ({ request }) => {
  await cleanup(request);
  const media = path.join(process.env.E2E_ROOT!, 'normal/media');
  expect((await request.put(`${backend}/settings/media-dir?media_dir=${encodeURIComponent(media)}`)).ok()).toBeTruthy();
  const scan = await request.post(`${backend}/library/scan?media_dir=${encodeURIComponent(media)}`);
  expect(scan.ok()).toBeTruthy();
  const { workflow_id } = await scan.json();
  await expect.poll(async () => (await read(request, `/workflows/${workflow_id}`)).status, { timeout: 45000 }).toBe('succeeded');
  films = await read(request, '/library/films');
  // Other interaction tests may add media to this owned synthetic directory.
  expect(films.length).toBeGreaterThanOrEqual(12);
});
test.afterAll(async ({ request }) => { await cleanup(request); });
test.beforeEach(async ({ context }) => {
  await context.route('**/*', route => ['127.0.0.1', 'localhost'].includes(new URL(route.request().url()).hostname)
    ? route.continue() : route.abort('blockedbyclient'));
});

async function capture(page: import('@playwright/test').Page, name: string) {
  await page.evaluate(() => document.fonts.ready);
  // Refresh the full composited frame without moving or blurring the focused control.
  await page.evaluate(async () => {
    const root = document.documentElement;
    const opacity = root.style.opacity;
    const frame = () => new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
    root.style.opacity = '0';
    await frame(); await frame();
    root.style.opacity = opacity;
    await frame(); await frame();
  });
  let clip;
  if (name === 'library-ui-hover.png' || name === 'library-ui-focus.png') {
    const image = (await page.locator('.library-card-media').first().boundingBox())!;
    const panel = (await page.locator('.library-card-inspector').first().boundingBox())!;
    clip = { ...image, height: panel.y + panel.height - image.y };
  }
  await page.screenshot({ path: path.join('e2e-artifacts', name), animations: 'disabled', clip });
}

test.describe('desktop with a mouse', () => {
  test.use({ hasTouch: false });
  for (const width of [1920, 1980]) test(`clean first screen and four columns at ${width}x1080`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1080 });
    await page.goto('/en/library');
    await expect(page.locator('a[id^="film-link-"]')).toHaveCount(films.length);
    await expect(page.getByRole('form', { name: 'Library filters' })).toHaveCount(0);
    await expect(page.locator('h1')).toHaveClass(/type-display-editorial/);
    await expect(page.getByRole('link', { name: 'Identity review', exact: true })).toHaveAttribute('href', '/en/library/identity-review');
    const grid = page.locator('.library-card-media').first().locator('..').locator('..').locator('..');
    expect(await grid.evaluate(el => getComputedStyle(el).gridTemplateColumns.split(' ').length)).toBe(4);
    for (const name of ['Filter', 'Sort', 'Scan for Films', 'More']) {
      const button = page.getByRole('button', { name, exact: true });
      await expect(button).toHaveAttribute('title', name);
      expect(await button.innerText()).toBe('');
      const style = await button.evaluate(el => ({ border: getComputedStyle(el).borderWidth, width: el.clientWidth, height: el.clientHeight }));
      expect(style.border).toBe('0px'); expect(style.width).toBeGreaterThanOrEqual(44); expect(style.height).toBeGreaterThanOrEqual(44);
    }
    await expect(page.locator('.library-card-touch-actions')).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await capture(page, `library-ui-${width}x1080.png`);
  });

  test('historic hover panel, safe adjacent actions, focus reveal and Escape', async ({ page, request }) => {
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto('/en/library');
    const media = page.locator('.library-card-media').first();
    const firstLink = media.locator('a[id^="film-link-"]');
    const firstId = (await firstLink.getAttribute('id'))!.replace('film-link-', '');
    const nextId = (await page.locator('a[id^="film-link-"]').nth(1).getAttribute('id'))!.replace('film-link-', '');
    const nextState = await read(request, `/films/${nextId}/profile-state`);
    const inspector = media.locator('.library-card-inspector');
    await expect(inspector).toBeHidden();
    await media.locator('a').hover();
    await expect(inspector).toBeVisible();
    await expect(inspector).toHaveCSS('opacity', '1');
    expect(await inspector.evaluate(el => Math.abs(el.getBoundingClientRect().top - el.parentElement!.getBoundingClientRect().bottom))).toBeLessThan(1);
    await expect(media.locator('.library-card-overlay')).toBeVisible();
    await capture(page, 'library-ui-hover.png');
    await inspector.hover();
    await inspector.getByRole('button', { name: 'Favorite', exact: true }).click();
    await expect.poll(async () => (await read(request, `/films/${firstId}/profile-state`)).favorite).toBe(true);
    expect((await read(request, `/films/${nextId}/profile-state`)).favorite).toBe(nextState.favorite);
    await firstLink.hover(); // Keep the pointer parked over the card during keyboard navigation.
    await page.keyboard.press('Escape');
    await expect(firstLink).toBeFocused();
    await expect(inspector).toBeHidden();
    await page.keyboard.press('Tab'); // Hidden inspector actions cannot take focus.
    await expect(page.locator('.library-card-title').first()).toBeFocused();
    await expect(page.locator('.library-card-title').first()).toHaveCSS('opacity', '1');
    await expect(inspector).toBeHidden();
    await page.mouse.move(0, 0);
    await firstLink.focus();
    await expect(inspector).toBeVisible();
    await page.keyboard.press('Tab');
    await expect(inspector.getByRole('button').first()).toBeFocused();
    await expect(inspector).toHaveCSS('opacity', '1');
    await capture(page, 'library-ui-focus.png');
    await page.keyboard.press('Escape');
    await expect(inspector).toBeHidden();
    await page.locator('.library-card-media').nth(1).locator('a').hover();
    await expect(page.locator('.library-card-inspector').nth(1)).toBeVisible();
    await expect(inspector).toBeHidden();
  });

  test('drawer is modal, closes to its trigger, retains applied ranges and sort', async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto('/en/library?sort=duration&dir=desc&q=Quiet&year_min=1900&duration_max=200');
    const filter = page.getByRole('button', { name: 'Filter', exact: true });
    await expect(filter).toHaveAttribute('aria-expanded', 'false');
    await expect(page.getByLabel('Applied filters', { exact: true })).toContainText('Quiet');
    await expect(filter).toHaveAccessibleDescription('3 active conditions');
    await filter.click();
    const dialog = page.getByRole('dialog', { name: 'Library filters', exact: true });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole('button', { name: 'Close filters', exact: true })).toBeFocused();
    await page.keyboard.press('Shift+Tab');
    await expect(dialog.getByRole('link', { name: 'Clear all conditions', exact: true })).toBeFocused();
    await page.keyboard.press('Tab');
    await expect(dialog.getByRole('button', { name: 'Close filters', exact: true })).toBeFocused();
    await expect(page.getByRole('link', { name: 'Identity review', exact: true })).toHaveCount(0); // Modal background is isolated.
    await expect(dialog.getByLabel('Earliest year', { exact: true })).toHaveValue('1900');
    await capture(page, 'library-ui-filter-drawer.png');
    await page.keyboard.press('Escape');
    await expect(filter).toBeFocused();
    await filter.click();
    await expect(dialog.getByLabel('Maximum duration', { exact: true })).toHaveValue('200');
    await dialog.getByRole('button', { name: 'Apply filters', exact: true }).click();
    await expect(filter).toHaveAttribute('aria-expanded', 'false');
    const params = new URL(page.url()).searchParams;
    expect(params.get('sort')).toBe('duration'); expect(params.get('dir')).toBe('desc'); expect(params.get('q')).toBe('Quiet');
  });
});

test('touch entry, narrow drawer, menu keyboard and Chinese layout remain usable', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/en/library');
  const trigger = page.locator('button[id^="film-link-"]').first();
  await expect(trigger).toBeVisible();
  await expect(page.locator('.library-card-touch-actions')).toHaveCount(0);
  expect((await trigger.boundingBox())!.width).toBeGreaterThan(300);
  await capture(page, 'library-ui-mobile.png');
  await trigger.tap();
  await expect(trigger).toHaveAttribute('aria-expanded', 'true');
  await expect(page.locator('.library-card-inspector').first()).toBeVisible();
  await expect(page.locator('.library-card-inspector').first()).toHaveCSS('opacity', '1');
  await capture(page, 'library-ui-touch-actions.png');
  await trigger.tap();
  await expect(page.locator('.library-card-inspector').first()).toBeHidden();
  await page.getByRole('button', { name: 'More', exact: true }).click();
  await page.getByRole('menuitem', { name: 'Activity', exact: true }).focus();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button', { name: 'More', exact: true })).toBeFocused();
  for (const [width, columns] of [[360, 1], [768, 2], [1024, 3], [1920, 4]]) {
    await page.setViewportSize({ width, height: 900 });
    const grid = page.locator('.library-card-media').first().locator('..').locator('..').locator('..');
    expect(await grid.evaluate(el => getComputedStyle(el).gridTemplateColumns.split(' ').length)).toBe(columns);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/zh/library?q=Quiet&year_min=1900');
  await page.getByRole('button', { name: '筛选', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('searchbox')).toHaveValue('Quiet');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(await dialog.evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
  await capture(page, 'library-ui-mobile-drawer-zh.png');
});

test('touch image disclosure keeps direct links, keyboard controls and adjacent taps usable', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/en/library');
  const originalURL = page.url();
  const images = page.locator('button[id^="film-link-"]');
  const first = images.first();
  const second = images.nth(1);
  const firstId = (await first.getAttribute('id'))!.replace('film-link-', '');
  const secondId = (await second.getAttribute('id'))!.replace('film-link-', '');
  const panel = page.locator('.library-card-inspector').first();
  const title = page.locator('.library-card-title').first();
  await expect(first).toHaveAttribute('aria-expanded', 'false');
  await first.focus();
  await expect(panel).toBeHidden();
  await page.keyboard.press('Tab');
  await expect(title).toBeFocused(); // Closed inspector links/actions are skipped.
  await first.focus();
  await page.keyboard.press('Enter');
  await expect(first).toHaveAttribute('aria-expanded', 'true');
  await page.keyboard.press('Tab');
  await expect(panel.getByRole('link', { name: 'View film details', exact: true })).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(first).toBeFocused();
  await expect(panel).toBeHidden();
  await page.keyboard.press('Space');
  await expect(panel).toBeVisible();
  await page.keyboard.press('Escape');

  await first.tap();
  await expect(page).toHaveURL(originalURL);
  await expect(panel.getByRole('link', { name: 'View film details', exact: true })).toHaveAttribute('href', `/en/library/${firstId}`);
  await expect(title).toBeVisible();
  await expect(title).toHaveCSS('opacity', '1');
  await expect(title).toHaveCSS('pointer-events', 'auto');
  const panelBounds = (await panel.boundingBox())!;
  expect((await second.boundingBox())!.y).toBeGreaterThanOrEqual(panelBounds.y + panelBounds.height);
  await second.tap(); // Closing the first panel must not move the target before activation.
  await expect(first).toHaveAttribute('aria-expanded', 'false');
  await expect(second).toHaveAttribute('aria-expanded', 'true');
  await expect(page.locator('.library-card-inspector').nth(1).getByRole('link', { name: 'View film details', exact: true }))
    .toHaveAttribute('href', `/en/library/${secondId}`);
  await expect(page).toHaveURL(originalURL);
  await page.locator('h1').tap();
  await expect(second).toHaveAttribute('aria-expanded', 'false');
  await expect(page.locator('.library-card-inspector').nth(1)).toBeHidden();

  await first.tap();
  await panel.getByRole('link', { name: 'View film details', exact: true }).tap();
  await expect(page).toHaveURL(new RegExp(`/en/library/${firstId}$`));
  await page.getByRole('button', { name: /^(Return to library|Back)$/i }).click();
  await expect(page).toHaveURL(originalURL);
  await expect(first).toBeFocused();
  await expect(first).toHaveAttribute('aria-expanded', 'false');
  await first.tap();
  await title.tap(); // The title is still a direct, single-activation link while expanded.
  await expect(page).toHaveURL(new RegExp(`/en/library/${firstId}$`));
  await page.getByRole('button', { name: /^(Return to library|Back)$/i }).click();
  await expect(first).toBeFocused();
  await page.reload();
  await expect(first).toBeFocused();
  await expect(first).toHaveAttribute('aria-expanded', 'false');
});
