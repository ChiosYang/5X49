import { test, expect, type APIRequestContext, type Page } from '@playwright/test';
import path from 'node:path';

const backend = process.env.E2E_BACKEND!;
const cards = (page: Page) => page.locator('[id^="film-link-"]');
const titles = (page: Page) => cards(page).locator('h2,h3').allTextContents();
let films: Record<string, string>;
async function control(request: APIRequestContext, action: string) {
  const response = await request.post(`${backend}/__e2e/control`, {
    headers: { 'x-e2e-token': process.env.E2E_TOKEN! }, data: { action } });
  expect(response.ok()).toBeTruthy(); return response.json();
}
test.beforeAll(async ({ request }) => {
  await control(request, 'identity_cleanup');
  films = await control(request, 'library_filter_fixture');
});
test.afterAll(async ({ request }) => { await control(request, 'identity_cleanup'); });
test.beforeEach(async ({ context }) => {
  await context.route('**/*', route => ['127.0.0.1', 'localhost'].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort('blockedbyclient'));
});

async function openFilters(page: Page) {
  if (!await page.getByRole('dialog', {name:'Library filters',exact:true}).isVisible())
    await page.getByRole('button', {name:'Filter',exact:true}).click();
}

async function combine(page: Page) {
  await page.goto('/en/library');
  await openFilters(page);
  await page.getByRole('searchbox', { name: 'Search library', exact: true }).fill('Orbit');
  await page.getByLabel('Watched status', { exact: true }).selectOption('watched');
  await page.getByLabel('Favorites only', { exact: true }).check();
  for (const [label, value] of [['Minimum duration','90'],['Maximum duration','120'],
    ['Minimum Film personal rating','3'],['Maximum Film personal rating','5'],['Earliest year','1999'],['Latest year','2001']])
    await page.getByRole('spinbutton', { name: label, exact: true }).fill(value);
  await page.getByRole('button', { name: 'Apply filters', exact: true }).click();
  await expect(cards(page)).toHaveCount(2);
  expect(await titles(page)).toEqual(['Orbit Dawn', 'Orbit Echo']);
  await expect(cards(page).first()).toHaveAttribute('type', 'button'); // Touch controls have hydrated after the native GET.
}

test('all conditions, sorting, reload, detail return and history retain one committed URL', async ({ page }) => {
  await combine(page);
  await page.getByRole('button', { name: 'Sort', exact: true }).click();
  await page.getByRole('link', { name: 'Duration', exact: true }).click();
  await expect.poll(() => titles(page)).toEqual(['Orbit Echo', 'Orbit Dawn']);
  const url = page.url();
  await page.reload();
  await openFilters(page);
  await expect(page.getByLabel('Minimum duration', { exact: true })).toHaveValue('90');
  await expect(page.getByLabel('Favorites only', { exact: true })).toBeChecked();
  await page.keyboard.press('Escape');
  const first = cards(page).first();
  const id = await first.getAttribute('id');
  await expect(first).toHaveAttribute("type", "button");
  await first.click();
  await page.getByRole("link", {name:"View film details",exact:true}).click();
  await page.getByRole('button', { name: /^(Return to library|Back)$/i }).click();
  await expect(page).toHaveURL(url);
  await expect(page.locator(`#${id}`)).toBeFocused();
  await openFilters(page);
  await page.getByLabel('Latest year', { exact: true }).fill('1999');
  await page.getByRole('button', { name: 'Apply filters', exact: true }).click();
  await expect(cards(page)).toHaveCount(1);
  await page.goBack();
  await expect(page).toHaveURL(url);
  await openFilters(page);
  await expect(page.getByLabel('Latest year', { exact: true })).toHaveValue('2001');
  await expect.poll(() => titles(page)).toEqual(['Orbit Echo', 'Orbit Dawn']);
});

test('empty, invalid ranges, clear all, legacy favorite and pagination are deterministic', async ({ page }) => {
  await combine(page);
  await openFilters(page);
  await page.getByRole('searchbox', { name: 'Search library', exact: true }).fill('no-match');
  await page.getByRole('button', { name: 'Apply filters', exact: true }).click();
  await expect(cards(page)).toHaveCount(0);
  await expect(page.getByText('No Films match the current filter.', { exact: true })).toBeVisible();
  await page.getByRole('link', { name: 'Clear all conditions', exact: true }).click();
  await expect(cards(page)).toHaveCount(40);
  await openFilters(page);
  for (const field of ['Minimum duration','Maximum duration','Minimum Film personal rating','Maximum Film personal rating','Earliest year','Latest year'])
    await expect(page.getByLabel(field, { exact: true })).toHaveValue('');
  await expect(page.getByLabel('Favorites only', { exact: true })).not.toBeChecked();
  await page.goto('/en/library?filter=favorite');
  await expect(cards(page)).toHaveCount(3);
  await openFilters(page);
  await expect(page.getByLabel('Favorites only', { exact: true })).toBeChecked();
  await page.goto('/en/library?q=Shelf&duration_min=80&duration_max=80&year_min=1980&year_max=1980');
  await expect(cards(page)).toHaveCount(40);
  await page.getByRole('link', { name: 'Next page', exact: true }).click();
  await expect(cards(page)).toHaveCount(2);
  expect(new URL(page.url()).searchParams.get('year_min')).toBe('1980');
  await openFilters(page);
  await page.getByLabel('Earliest year', { exact: true }).fill('2001');
  const before = page.url();
  await page.getByRole('button', { name: 'Apply filters', exact: true }).click();
  await expect(page.getByRole('form', {name:'Library filters'}).getByRole('alert')).toContainText('Check Release year');
  expect(page.url()).toBe(before);
  await page.goto('/en/library?duration_min=120&duration_max=90');
  await openFilters(page);
  await expect(page.getByRole('form', {name:'Library filters'}).getByRole('alert')).toContainText('Check Duration');
  await expect(cards(page)).toHaveCount(0);
});

test('search handoff, unsubmitted drafts and consecutive applies do not show stale results', async ({ page }) => {
  await page.goto('/en/search?q=Orbit');
  await page.getByRole('link', { name: 'Refine in Library', exact: true }).click();
  await openFilters(page);
  await expect(page.getByRole('searchbox', { name: 'Search library', exact: true })).toHaveValue('Orbit');
  await expect(cards(page)).toHaveCount(5);
  await page.getByLabel('Minimum duration', { exact: true }).fill('120');
  await expect(cards(page)).toHaveCount(5);
  await page.reload();
  await openFilters(page);
  await expect(page.getByLabel('Minimum duration', { exact: true })).toHaveValue('');
  const submissions: string[] = [];
  page.on('request', request => {
    const url = new URL(request.url());
    if (request.isNavigationRequest() && url.pathname === '/en/library') submissions.push(url.searchParams.get('q') || '');
  });
  for (const query of ['Orbit Dawn', 'Orbit Echo', 'Orbit Dawn']) {
    await openFilters(page);
    await page.getByRole('searchbox', { name: 'Search library', exact: true }).fill(query);
    await page.getByRole('button', { name: 'Apply filters', exact: true }).dblclick();
    await expect(cards(page).locator('h2,h3')).toHaveText([query]);
  }
  expect(submissions).toEqual(['Orbit Dawn', 'Orbit Echo', 'Orbit Dawn']);
});

test('favorite plus watched mutation reconciles without restoring a removed card', async ({ page, request }) => {
  await combine(page);
  const response = await request.put(`${backend}/films/${films['Orbit Dawn']}/profile-state`, { data: { favorite: false } });
  expect(response.ok()).toBeTruthy();
  await expect(cards(page)).toHaveCount(1);
  await page.reload();
  expect(await titles(page)).toEqual(['Orbit Echo']);
  expect((await request.put(`${backend}/films/${films['Orbit Dawn']}/profile-state`, { data: { favorite: true } })).ok()).toBeTruthy();
});

for (const locale of ['en', 'zh']) test(`a mutation before event subscription reconciles in ${locale} despite a stale locale cookie`, async ({ page, request }) => {
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/library/events', async route => {
    await gate;
    // The initial document's stream can be cancelled by the filter navigation.
    await route.continue().catch(() => {});
  });
  try {
    await combine(page);
    if (locale === 'zh') {
      const localized = new URL(page.url());
      localized.pathname = '/zh/library';
      await page.goto(localized.toString());
      await expect(cards(page)).toHaveCount(2);
    }
    await expect(page.locator('html')).toHaveAttribute('lang', locale);
    expect((await request.put(`${backend}/films/${films['Orbit Dawn']}/profile-state`, { data: { favorite: false } })).ok()).toBeTruthy();
    // No subscriber existed for this mutation; replaying an event is not required.
    await expect(cards(page)).toHaveCount(2);
    // A prefetch response from the previous locale can arrive after navigation.
    await page.context().addCookies([{ name: 'NEXT_LOCALE', value: locale === 'zh' ? 'en' : 'zh', domain: new URL(page.url()).hostname, path: '/' }]);
    release();
    await expect.poll(() => titles(page)).toEqual(['Orbit Echo']);
    await expect(page.locator('html')).toHaveAttribute('lang', locale);
    await page.reload();
    await expect.poll(() => titles(page)).toEqual(['Orbit Echo']);
    await expect(page.locator('html')).toHaveAttribute('lang', locale);
  } finally {
    release();
    expect((await request.put(`${backend}/films/${films['Orbit Dawn']}/profile-state`, { data: { favorite: true } })).ok()).toBeTruthy();
  }
});

test('prefetching the previous language cannot overwrite the current locale cookie', async ({ request }) => {
  const previous = await request.get('/en/search', { headers: { cookie: 'NEXT_LOCALE=zh', 'next-router-prefetch': '1' } });
  expect(previous.ok()).toBeTruthy();
  expect(previous.headers()['set-cookie'] || '').not.toContain('NEXT_LOCALE=');
  const navigation = await request.get('/en/search', { headers: { cookie: 'NEXT_LOCALE=zh' } });
  expect(navigation.ok()).toBeTruthy();
  expect(navigation.headers()['set-cookie']).toContain('NEXT_LOCALE=en');
});

test('only personal overall stars match; external and Viewing scores cannot fill an unrated Film', async ({ page, request }) => {
  await page.goto('/en/library?q=Orbit&rating_min=5&rating_max=5');
  await expect.poll(() => titles(page)).toEqual(['Orbit Echo']);
  await openFilters(page);
  await expect(page.getByLabel('Minimum Film personal rating', {exact:true})).toHaveValue('5');
  await page.keyboard.press('Escape');
  expect((await request.put(`${backend}/films/${films['Orbit Echo']}/profile-state`, {data:{rating:2}})).ok()).toBeTruthy();
  await expect(cards(page)).toHaveCount(0);
  await page.reload();
  await expect(cards(page)).toHaveCount(0);
  expect((await request.put(`${backend}/films/${films['Orbit Echo']}/profile-state`, {data:{rating:5}})).ok()).toBeTruthy();
  await page.goto('/en/library?q=Orbit&rating_min=1');
  await expect.poll(() => titles(page)).toEqual(['Orbit Dawn','Orbit Echo','Orbit Else']);
  await page.getByRole('link',{name:'Clear all conditions',exact:true}).click();
  await expect(page.locator(`#film-link-${films['Orbit Unknown']}`)).toBeVisible();
});

test('a delayed earlier document response cannot replace a newer filter navigation', async ({ page }) => {
  await page.goto('/en/library');
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  let reached!: () => void;
  const waiting = new Promise<void>(resolve => { reached = resolve; });
  await page.route(url => url.pathname === '/en/library' && url.searchParams.get('q') === 'Orbit Dawn', async route => {
    const response = await route.fetch();
    reached();
    await gate;
    await route.fulfill({ response }).catch(() => {}); // A cancelled document is expected.
  });
  const earlier = page.goto('/en/library?q=Orbit%20Dawn').catch(error => {
    expect(String(error)).toMatch(/ERR_ABORTED|interrupted/i);
  });
  await waiting;
  await page.goto('/en/library?q=Orbit%20Echo');
  release();
  await earlier;
  await expect.poll(() => titles(page)).toEqual(['Orbit Echo']);
  await openFilters(page);
  await expect(page.getByRole('searchbox', {name:'Search library',exact:true})).toHaveValue('Orbit Echo');
});

test('desktop and narrow Chinese layout preserve title/navigation and expose all controls', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.goto('/zh/library?q=Orbit&filter=watched&favorite=true&duration_min=90&duration_max=120&rating_min=3&rating_max=5&year_min=1999&year_max=2001');
  await expect(cards(page)).toHaveCount(2);
  await expect(page.locator('h1')).toHaveClass(/type-display-editorial/);
  await page.screenshot({ path: path.join('e2e-artifacts', 'library-filters-desktop-zh.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('button', {name:'筛选',exact:true}).click();
  await expect(page.getByRole('button', { name: '应用筛选', exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: path.join('e2e-artifacts', 'library-filters-narrow-zh.png'), fullPage: true });
  expect(errors).toEqual([]);
});
