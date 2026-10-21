import { test, expect, type APIRequestContext, type Page } from '@playwright/test';
import path from 'node:path';
import en from '../messages/en.json';
import zh from '../messages/zh.json';
import type { ExploreCollections, ExploreFacetSummary, ExploreFilmPage } from '../src/types/movie';

const backend = process.env.E2E_BACKEND!;
const cards = (page: Page) => page.locator('[id^="film-link-"]');
const results = (page: Page) => page.locator('#explore-results-title');

async function read(request: APIRequestContext, url: string) {
  const response = await request.get(`${backend}${url}`);
  expect(response.ok()).toBeTruthy(); return response.json();
}
async function control(request: APIRequestContext, action: string) {
  const response = await request.post(`${backend}/__e2e/control`, {
    headers: { 'x-e2e-token': process.env.E2E_TOKEN! }, data: { action },
  });
  expect(response.ok()).toBeTruthy(); return response.json();
}
async function capture(page: Page, name: string) {
  await page.evaluate(async () => {
    await document.fonts.ready;
    await Promise.all([...document.images].filter(image => {
      const bounds = image.getBoundingClientRect();
      return bounds.bottom > 0 && bounds.top < innerHeight && bounds.right > 0 && bounds.left < innerWidth;
    }).map(image => image.decode().catch(() => {})));
    // Chrome on Windows can retain an old composited frame after decoding local artwork.
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
async function noOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
}

async function singleUnwatchedCountry(request: APIRequestContext) {
  const targetPage: ExploreFilmPage = await read(request, '/explore/films?country=DE');
  expect(targetPage.total).toBe(1);
  const target = targetPage.items[0].film;
  const countries: { items: ExploreFacetSummary[] } = await read(request, '/explore/facets/country?limit=100');
  const params = new URLSearchParams({ limit: '100' });
  countries.items.forEach(country => params.append('country', country.key));
  const films: ExploreFilmPage = await read(request, `/explore/films?${params}`);
  for (const { film } of films.items) {
    const saved = await request.put(`${backend}/films/${film.id}/profile-state`, {
      data: film.id === target.id ? { watched: false, favorite: false } : { watched: true },
    });
    expect(saved.ok()).toBeTruthy();
  }
  return target;
}

const firstShelfPage = '/en/explore?decade=1980&view=unwatched&sort=year&dir=asc';
async function lastUnwatchedPage(request: APIRequestContext) {
  const all: ExploreFilmPage = await read(request, '/explore/films?decade=1980&sort=year&dir=asc&limit=100');
  expect(all.total).toBe(42);
  for (const { film } of all.items) {
    if (film.profile_state.watched) expect((await request.put(`${backend}/films/${film.id}/profile-state`, { data: { watched: false } })).ok()).toBeTruthy();
  }
  expect((await request.put(`${backend}/films/${all.items[0].film.id}/profile-state`, { data: { watched: true } })).ok()).toBeTruthy();
  const last: ExploreFilmPage = await read(request, '/explore/films?decade=1980&view=unwatched&sort=year&dir=asc&offset=40');
  expect(last.total).toBe(41); expect(last.items).toHaveLength(1);
  return last.items[0].film;
}

test.beforeAll(async ({ request }) => {
  await control(request, 'identity_cleanup');
  const media = path.join(process.env.E2E_ROOT!, 'normal/media');
  const saved = await request.put(`${backend}/settings/media-dir?media_dir=${encodeURIComponent(media)}`);
  expect(saved.ok()).toBeTruthy();
  const { media_dir } = await saved.json();
  const scan = await request.post(`${backend}/library/scan?media_dir=${encodeURIComponent(media_dir)}`);
  expect(scan.ok()).toBeTruthy();
  const { workflow_id } = await scan.json();
  await expect.poll(async () => (await read(request, `/workflows/${workflow_id}`)).status, { timeout: 45000 }).toBe('succeeded');
  await control(request, 'library_filter_fixture'); // 47 more real local Films, watched states and pagination.
});
test.afterAll(async ({ request }) => { await control(request, 'identity_cleanup'); });
test.beforeEach(async ({ context }) => {
  await context.route('**/*', route => ['127.0.0.1', 'localhost'].includes(new URL(route.request().url()).hostname)
    ? route.continue() : route.abort('blockedbyclient'));
});

for (const [locale, copy] of [['en', en.Explore], ['zh', zh.Explore]] as const) {
  for (const width of [1920, 1024, 768, 390, 320]) {
    test(`${locale} Explore browses concrete collections and searches all categories at ${width}px`, async ({ page, request }) => {
      const errors: string[] = [], ai: string[] = [];
      page.on('pageerror', error => errors.push(error.message));
      page.on('request', request => { if (request.method() === 'POST' && /\/(ask|analysis)/.test(request.url())) ai.push(request.url()); });
      await page.setViewportSize({ width, height: width === 1920 ? 1080 : 844 });
      await page.goto(`/${locale}/explore`);
      await expect(page.locator('h1')).toHaveClass('type-display-editorial');
      const collectionSection = page.getByRole('region', { name: copy.collectionsTitle, exact: true });
      const collections: ExploreCollections = await read(request, '/explore/collections');
      expect(collections.items.length).toBeGreaterThan(0);
      await expect(collectionSection.getByRole('button')).toHaveCount(collections.items.length);
      await expect(cards(page)).toHaveCount(40);
      await expect(page.getByText(copy.findFact, { exact: true })).toHaveCount(0);
      await expect(page.getByText(copy.currentLens, { exact: true })).toHaveCount(0);
      await noOverflow(page);
      if (width === 1920 || width === 390) await capture(page, `explore-collections-${locale}-${width}.png`);
      await collectionSection.getByRole('button').first().click();
      const first = collections.items[0];
      await expect.poll(() => new URL(page.url()).searchParams.get(first.dimension)).toBe(first.key);
      await expect(results(page)).toHaveText(new RegExp(`^${first.count}\\b`));
      await page.getByRole('button', { name: copy.clearAll, exact: true }).click();
      await expect.poll(() => new URL(page.url()).searchParams.has(first.dimension)).toBe(false);
      // Collection country suggestions may explicitly select Unwatched; reset to All.
      await page.getByRole('group', { name: copy.viewLabel, exact: true }).getByRole('button', { name: copy.views.all, exact: true }).click();
      const search = page.getByRole('textbox', { name: copy.searchAll, exact: true });
      await search.fill(locale === 'zh' ? '日本' : 'Japan');
      const finder = page.getByRole('region', { name: copy.searchTitle, exact: true });
      for (const label of Object.values(copy.dimensions)) await expect(finder.getByRole('region', { name: label, exact: true })).toBeVisible();
      const country = finder.getByRole('region', { name: copy.dimensions.country, exact: true });
      const countryName = new Intl.DisplayNames([locale], { type: 'region' }).of('JP')!;
      await country.getByRole('button').filter({ has: page.getByText(countryName, { exact: true }) }).click();
      await expect.poll(() => new URL(page.url()).searchParams.get('country')).toBe('JP');
      const filtered = await read(request, '/explore/films?country=JP');
      await expect(results(page)).toHaveText(new RegExp(`^${filtered.total}\\b`));
      await expect(search).toHaveValue(locale === 'zh' ? '日本' : 'Japan');
      expect(new URL(page.url()).searchParams.has('q')).toBe(false);
      const selected = page.getByRole('region', { name: copy.activeFilters, exact: true });
      await expect(selected).toBeVisible();
      await noOverflow(page);
      if (width === 1920 || width === 390) {
        await search.scrollIntoViewIfNeeded(); await capture(page, `explore-filters-${locale}-${width}.png`);
        await results(page).scrollIntoViewIfNeeded(); await capture(page, `explore-results-${locale}-${width}.png`);
      }
      await selected.getByRole('button', { name: copy.removeFact.replace('{fact}', countryName), exact: true }).click();
      await expect.poll(() => new URL(page.url()).searchParams.has('country')).toBe(false);
      await search.focus(); await page.keyboard.press('Escape'); await expect(search).toHaveValue('');
      await page.locator('h1').click(); await page.keyboard.press('/'); await expect(search).toBeFocused();
      expect(ai).toEqual([]); expect(errors).toEqual([]);
    });
  }
}

test('people intersections, legacy union URLs, viewing, sort and history remain explicit', async ({ page, request }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  const people: ExploreFacetSummary[] = (await read(request, '/explore/facets/person?limit=100')).items;
  const director = people.find(person => person.label === 'Director 1')!;
  const actor = people.find(person => person.label === 'Actor 1')!;
  expect(director).toBeTruthy(); expect(actor).toBeTruthy();
  const params = `person=${director.key}&person=${actor.key}`;
  const all = await read(request, `/explore/films?${params}&person_match=all`);
  const any = await read(request, `/explore/films?${params}`);
  expect(all.total).toBeGreaterThan(0); expect(any.total).toBeGreaterThan(all.total);
  await page.goto('/en/explore');
  const search = page.getByRole('textbox', { name: en.Explore.searchAll, exact: true });
  const finder = page.getByRole('region', { name: en.Explore.searchTitle, exact: true });
  for (const person of [director, actor]) {
    await search.fill(person.label);
    await finder.getByRole('region', { name: 'Person', exact: true }).getByRole('button').filter({ has: page.getByText(person.label, { exact: true }) }).click();
    await expect.poll(() => new URL(page.url()).searchParams.getAll('person').includes(person.key)).toBe(true);
  }
  await expect(results(page)).toHaveText(`${all.total} Film`);
  await expect(page.getByRole('button', { name: 'Match all', exact: true })).toHaveAttribute('aria-pressed', 'true');
  const allUrl = page.url();
  await page.getByRole('button', { name: 'Match any', exact: true }).click();
  await expect(results(page)).toHaveText(`${any.total} Films`);
  const anyUrl = page.url();
  await page.goBack(); await expect(page).toHaveURL(allUrl); await expect(results(page)).toHaveText(`${all.total} Film`);
  await page.goForward(); await expect(page).toHaveURL(anyUrl); await page.reload();
  await expect(page.getByRole('button', { name: 'Match any', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await page.goto(`/en/explore?${params}`);
  await expect(results(page)).toHaveText(`${any.total} Films`);
  await expect(page.getByRole('button', { name: 'Match any', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('button', { name: 'Year', exact: true }).click();
  await expect.poll(() => new URL(page.url()).searchParams.get('sort')).toBe('year');
  await page.getByRole('button', { name: 'Watched', exact: true }).click();
  await expect.poll(() => new URL(page.url()).searchParams.get('view')).toBe('watched');
  const watchedUrl = page.url(); await page.reload(); await expect(page).toHaveURL(watchedUrl);
});

test('pagination focuses results, detail return preserves URL, and unknown filters stay strict', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/en/explore');
  await page.getByRole('button', { name: 'Next', exact: true }).click();
  await expect.poll(() => new URL(page.url()).searchParams.get('offset')).toBe('40');
  await expect(results(page)).toBeFocused();
  const paged = page.url();
  await page.reload(); await expect(page).toHaveURL(paged); await expect(cards(page)).toHaveCount(19);
  await page.locator('.library-card-title').first().click();
  await expect(page).toHaveURL(/\/library\/film_[a-f0-9]{32}$/);
  await page.goBack(); await expect(page).toHaveURL(paged);
  await expect(cards(page)).toHaveCount(19);
  await page.goBack(); await expect.poll(() => new URL(page.url()).searchParams.has('offset')).toBe(false);
  await page.goto('/en/explore?country=ZZ');
  await expect(results(page)).toHaveText('0 Films');
  await expect(page.getByRole('heading', { name: en.Explore.zeroTitle, exact: true })).toBeVisible();
  await expect(page.getByRole('region', { name: en.Explore.activeFilters, exact: true }).getByText('Unavailable', { exact: true })).toBeVisible();
  expect(new URL(page.url()).searchParams.get('country')).toBe('ZZ');
});

test('late responses cannot restore old search results or leak the search text into the URL', async ({ page }) => {
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/explore/facets/*?*', async route => {
    if (new URL(route.request().url()).searchParams.get('q') === 'Director') await held;
    await route.continue();
  });
  await page.goto('/en/explore');
  const search = page.getByRole('textbox', { name: en.Explore.searchAll, exact: true });
  const finder = page.getByRole('region', { name: en.Explore.searchTitle, exact: true });
  const waiting = page.waitForRequest(request => new URL(request.url()).searchParams.get('q') === 'Director');
  await search.fill('Director'); await waiting;
  await search.fill('Actor');
  await expect(finder.getByText('Actor 1', { exact: true })).toBeVisible();
  release();
  await expect(finder.getByText('Director 1', { exact: true })).toHaveCount(0);
  expect(new URL(page.url()).search).toBe('');
});

test('filter searches paginate independently and recover a failed category read', async ({ page }) => {
  let failed = true;
  await page.route('**/api/explore/facets/person?*', route => failed
    ? route.fulfill({ status: 503, json: { detail: 'Fixture read unavailable' } }) : route.continue());
  await page.goto('/en/explore');
  const finder = page.getByRole('region', { name: en.Explore.searchTitle, exact: true });
  await finder.getByRole('button', { name: 'Person', exact: true }).click();
  const people = finder.getByRole('region', { name: 'Person', exact: true });
  await expect(people.getByText(en.Explore.facetLoadFailed)).toBeVisible();
  failed = false;
  await people.getByRole('button', { name: 'Retry', exact: true }).click();
  await expect(people.getByRole('button').filter({ has: page.getByText('Director 1', { exact: true }) })).toBeVisible();
  await people.getByRole('button', { name: 'Load more', exact: true }).click();
  await expect.poll(() => people.getByRole('button').count()).toBe(13);
  await page.getByRole('textbox', { name: en.Explore.searchAll, exact: true }).fill('Actor');
  await expect(people.getByText('Director 1', { exact: true })).toHaveCount(0);
  await expect.poll(() => people.getByRole('button').count()).toBe(7);
  expect(new URL(page.url()).search).toBe('');
});

test('rapid filter selections keep both conditions when an older navigation finishes last', async ({ page, request }) => {
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  await page.goto('/en/explore');
  const search = page.getByRole('textbox', { name: en.Explore.searchAll, exact: true });
  const finder = page.getByRole('region', { name: en.Explore.searchTitle, exact: true });
  await search.fill('Japan');
  await expect(finder.getByText('Japan', { exact: true })).toBeVisible();
  await page.route('**/en/explore?**', async route => {
    const params = new URL(route.request().url()).searchParams;
    if (params.get('country') === 'JP' && !params.has('person')) await held;
    await route.continue();
  });
  const waiting = page.waitForRequest(request => {
    const url = new URL(request.url());
    return url.pathname === '/en/explore' && url.searchParams.get('country') === 'JP';
  });
  await finder.getByRole('region', { name: 'Country', exact: true }).getByRole('button').click();
  await waiting;
  await search.fill('Actor 1');
  await finder.getByRole('region', { name: 'Person', exact: true }).getByRole('button').filter({ has: page.getByText('Actor 1', { exact: true }) }).click();
  await expect.poll(() => new URL(page.url()).searchParams.getAll('person').length).toBe(1);
  const committed = page.url();
  const params = new URL(committed).searchParams;
  expect(params.get('country')).toBe('JP');
  release();
  const expected = await read(request, `/explore/films?${params}`);
  await expect(results(page)).toHaveText(new RegExp(`^${expected.total}\\b`));
  await expect(page).toHaveURL(committed);
});

for (const width of [1440, 390]) {
  test(`saved card changes refresh default collections once without changing history or scroll at ${width}px`, async ({ page, request }) => {
    const target = await singleUnwatchedCountry(request);
    await page.setViewportSize({ width, height: 1000 });
    await page.goto('/en/library');
    const previous = page.url();
    await page.goto('/en/explore?sort=year');
    const href = page.url();
    const history = await page.evaluate(() => window.history.length);
    const collection = page.getByRole('region', { name: en.Explore.collectionsTitle, exact: true })
      .getByRole('button').filter({ has: page.getByText('Unwatched films from Germany', { exact: true }) });
    await expect(collection).toHaveCount(1);
    await expect(collection.getByText('1 Film · Unwatched', { exact: true })).toBeVisible();
    const writes: string[] = [], refreshes: string[] = [];
    page.on('request', request => {
      const url = new URL(request.url());
      if (url.pathname === `/api/films/${target.id}/profile-state` && request.method() === 'PUT') writes.push(request.postData()!);
      if (url.pathname === '/en/explore' && request.headers().rsc === '1') refreshes.push(request.url());
    });
    const trigger = page.locator(`#film-link-${target.id}`);
    await trigger.click();
    const panel = page.locator('.library-card-media').filter({ has: trigger }).locator('.library-card-inspector');
    const refreshed = page.waitForResponse(response => new URL(response.url()).pathname === '/en/explore' && response.request().headers().rsc === '1' && response.ok());
    await panel.getByRole('button', { name: en.Library.favorite, exact: true }).click();
    await refreshed;
    await expect(page.locator('[aria-labelledby="explore-results-title"] [aria-busy]')).toHaveAttribute('aria-busy', 'false');
    await expect(panel.getByRole('button', { name: en.Library.unfavorite, exact: true })).toBeVisible();
    expect(refreshes).toHaveLength(1); expect(writes).toHaveLength(1);
    const watched = panel.getByRole('button', { name: en.Library.markWatched, exact: true });
    await watched.scrollIntoViewIfNeeded();
    const scrollY = await page.evaluate(() => window.scrollY);
    await watched.click();
    await expect(collection).toHaveCount(0);
    expect(refreshes).toHaveLength(2); expect(writes).toHaveLength(2);
    await expect(page).toHaveURL(href);
    expect(await page.evaluate(() => window.history.length)).toBe(history);
    await expect.poll(() => page.evaluate(before => Math.abs(window.scrollY - Math.max(0,
      Math.min(before, document.documentElement.scrollHeight - innerHeight))), scrollY)).toBeLessThanOrEqual(1);
    await page.goBack(); await expect(page).toHaveURL(previous);
  });

  test(`marking a result watched refreshes the active Unwatched set and count at ${width}px`, async ({ page, request }) => {
    const target = await singleUnwatchedCountry(request);
    await page.setViewportSize({ width, height: 1000 });
    await page.goto('/en/library');
    const previous = page.url();
    await page.goto('/en/explore?country=DE&view=unwatched&sort=year');
    const href = page.url();
    const history = await page.evaluate(() => window.history.length);
    await expect(results(page)).toHaveText('1 Film');
    const writes: string[] = [], refreshes: string[] = [];
    page.on('request', request => {
      const url = new URL(request.url());
      if (url.pathname === `/api/films/${target.id}/profile-state` && request.method() === 'PUT') writes.push(request.postData()!);
      if (url.pathname === '/en/explore' && request.headers().rsc === '1') refreshes.push(request.url());
    });
    const trigger = page.locator(`#film-link-${target.id}`);
    await trigger.click();
    const watched = page.locator('.library-card-media').filter({ has: trigger }).getByRole('button', { name: en.Library.markWatched, exact: true });
    await watched.scrollIntoViewIfNeeded();
    const scrollY = await page.evaluate(() => window.scrollY);
    await watched.click();
    await expect(results(page)).toHaveText('0 Films');
    await expect(trigger).toHaveCount(0);
    await expect(page.getByRole('heading', { name: en.Explore.zeroTitle, exact: true })).toBeVisible();
    expect(refreshes).toHaveLength(1); expect(writes).toHaveLength(1);
    await expect(page).toHaveURL(href);
    expect(await page.evaluate(() => window.history.length)).toBe(history);
    await expect.poll(() => page.evaluate(before => Math.abs(window.scrollY - Math.max(0,
      Math.min(before, document.documentElement.scrollHeight - innerHeight))), scrollY)).toBeLessThanOrEqual(1);
    await page.goBack(); await expect(page).toHaveURL(previous);
  });
}

test('a 41-to-40 save replaces the invalid last page and never shows a false zero result', async ({ page, request }) => {
  const target = await lastUnwatchedPage(request);
  await page.goto('/en/library'); const previous = page.url();
  await page.goto(firstShelfPage);
  await expect(results(page)).toHaveText('41 Films');
  await page.getByRole('button', { name: 'Next', exact: true }).click();
  await expect(cards(page)).toHaveCount(1);
  const history = await page.evaluate(() => window.history.length);
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  const requests: URL[] = []; let writes = 0;
  await page.route('**/en/explore?**', async route => {
    const url = new URL(route.request().url());
    if (route.request().headers().rsc === '1') {
      requests.push(url);
      if (!url.searchParams.has('offset')) await held;
    }
    await route.continue();
  });
  page.on('request', request => { if (request.method() === 'PUT' && new URL(request.url()).pathname === `/api/films/${target.id}/profile-state`) writes++; });
  try {
    const trigger = page.locator(`#film-link-${target.id}`);
    await trigger.click();
    const corrected = page.waitForRequest(request => new URL(request.url()).pathname === '/en/explore' && !new URL(request.url()).searchParams.has('offset') && request.headers().rsc === '1');
    await page.locator('.library-card-media').filter({ has: trigger }).getByRole('button', { name: en.Library.markWatched, exact: true }).click();
    await corrected;
    await expect(results(page)).toHaveText('40 Films');
    await expect(page.getByRole('heading', { name: en.Explore.zeroTitle, exact: true })).toHaveCount(0);
    release();
    await expect(page).toHaveURL(new URL(firstShelfPage, page.url()).href);
    await expect(cards(page)).toHaveCount(40);
    await expect(results(page)).toHaveText('40 Films');
    expect(writes).toBe(1); expect(requests).toHaveLength(2);
    expect(requests[0].searchParams.get('offset')).toBe('40');
    expect(requests[1].searchParams.has('offset')).toBe(false);
    expect(await page.evaluate(() => window.history.length)).toBe(history);
    await page.goBack(); await expect(page).toHaveURL(new URL(firstShelfPage, page.url()).href);
    await page.goBack(); await expect(page).toHaveURL(previous);
  } finally { release(); }
});

test('a late invalid-page response cannot replace newer filter navigation', async ({ page, request }) => {
  const target = await lastUnwatchedPage(request);
  await page.goto(firstShelfPage);
  await page.getByRole('button', { name: 'Next', exact: true }).click();
  await expect(cards(page)).toHaveCount(1);
  let release!: () => void, captured!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  const fetched = new Promise<void>(resolve => { captured = resolve; });
  const requests: URL[] = [];
  await page.route('**/en/explore?**', async route => {
    const url = new URL(route.request().url());
    if (route.request().headers().rsc === '1') requests.push(url);
    if (url.searchParams.get('offset') === '40') {
      const response = await route.fetch(); captured(); await held;
      await route.fulfill({ response }).catch(() => {}); // A newer navigation may cancel this stale response.
    } else await route.continue();
  });
  try {
    const trigger = page.locator(`#film-link-${target.id}`);
    await trigger.click();
    await page.locator('.library-card-media').filter({ has: trigger }).getByRole('button', { name: en.Library.markWatched, exact: true }).click();
    await fetched;
    const history = await page.evaluate(() => window.history.length);
    await page.getByRole('group', { name: en.Explore.viewLabel, exact: true }).getByRole('button', { name: 'All', exact: true }).click();
    const search = page.getByRole('textbox', { name: en.Explore.searchAll, exact: true });
    await search.fill('Shelf'); await expect(search).toBeFocused();
    release();
    await expect(page).toHaveURL(new URL('/en/explore?decade=1980&sort=year&dir=asc', page.url()).href);
    await expect(results(page)).toHaveText('42 Films');
    await expect(page.locator('[aria-labelledby="explore-results-title"] [aria-busy]')).toHaveAttribute('aria-busy', 'false');
    await expect(search).toHaveValue('Shelf'); await expect(search).toBeFocused();
    expect(new URL(page.url()).searchParams.has('view')).toBe(false);
    expect(requests).toHaveLength(2);
    expect(await page.evaluate(() => window.history.length)).toBe(history + 1);
  } finally { release(); }
});

test('a delayed card save waits for pending filter navigation without clearing search or taking focus', async ({ page, request }) => {
  const target = await singleUnwatchedCountry(request);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto('/en/explore?sort=year');
  let release!: () => void, releaseView!: () => void, capturedView!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  const viewHeld = new Promise<void>(resolve => { releaseView = resolve; });
  const viewReady = new Promise<void>(resolve => { capturedView = resolve; });
  let writes = 0, trackRefresh = false, holdFirstView = true;
  const refreshes: string[] = [];
  await page.route(`**/api/films/${target.id}/profile-state`, async route => {
    if (route.request().method() === 'PUT') { writes++; await held; }
    await route.continue();
  });
  await page.route('**/en/explore?**', async route => {
    const params = new URL(route.request().url()).searchParams;
    if (holdFirstView && params.get('country') === 'DE' && params.get('view') === 'watched') {
      holdFirstView = false;
      const response = await route.fetch(); capturedView(); await viewHeld;
      await route.fulfill({ response }).catch(() => {});
    } else await route.continue();
  });
  page.on('request', request => {
    if (trackRefresh && new URL(request.url()).pathname === '/en/explore' && request.headers().rsc === '1') refreshes.push(request.url());
  });
  try {
    const trigger = page.locator(`#film-link-${target.id}`);
    await trigger.click();
    await page.locator('.library-card-media').filter({ has: trigger }).getByRole('button', { name: en.Library.markWatched, exact: true }).click();
    await expect.poll(() => writes).toBe(1);
    const search = page.getByRole('textbox', { name: en.Explore.searchAll, exact: true });
    await search.fill('Germany');
    await page.getByRole('region', { name: 'Country', exact: true }).getByRole('button').click();
    await expect.poll(() => new URL(page.url()).searchParams.get('country')).toBe('DE');
    const beforeView = page.url(), history = await page.evaluate(() => window.history.length);
    await page.getByRole('button', { name: 'Watched', exact: true }).click();
    await viewReady; // The new query's RSC response is still pending and contains the pre-save result.
    await search.focus();
    trackRefresh = true;
    release();
    await expect.poll(async () => (await read(request, `/films/${target.id}/profile-state`)).watched).toBe(true);
    await expect(search).toBeFocused(); await expect(search).toHaveValue('Germany');
    releaseView();
    await expect.poll(() => new URL(page.url()).searchParams.get('view')).toBe('watched');
    await expect(results(page)).toHaveText('1 Film');
    await expect(search).toHaveValue('Germany'); await expect(search).toBeFocused();
    expect(writes).toBe(1); expect(refreshes).toHaveLength(1);
    expect(new URL(refreshes[0]).searchParams.get('country')).toBe('DE');
    expect(new URL(refreshes[0]).searchParams.get('view')).toBe('watched');
    expect(await page.evaluate(() => window.history.length)).toBe(history + 1);
    await page.goBack(); await expect(page).toHaveURL(beforeView);
  } finally { release(); releaseView(); }
});

test('a save completing after detail navigation cannot refresh the new page or steal its focus', async ({ page, request }) => {
  const target = await singleUnwatchedCountry(request);
  await page.setViewportSize({ width: 390, height: 1000 });
  await page.goto('/en/explore?sort=year');
  const exploreHref = page.url();
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  let writes = 0, trackRefresh = false;
  const refreshes: string[] = [];
  await page.route(`**/api/films/${target.id}/profile-state`, async route => {
    if (route.request().method() === 'PUT') { writes++; await held; }
    await route.continue();
  });
  page.on('request', request => {
    const pathname = new URL(request.url()).pathname;
    if (trackRefresh && request.headers().rsc === '1' && request.headers()['next-router-prefetch'] !== '1'
        && (pathname === '/en/explore' || pathname === `/en/library/${target.id}`)) refreshes.push(request.url());
  });
  try {
    const trigger = page.locator(`#film-link-${target.id}`);
    await trigger.click();
    await page.locator('.library-card-media').filter({ has: trigger }).getByRole('button', { name: en.Library.markWatched, exact: true }).click();
    await expect.poll(() => writes).toBe(1);
    await page.keyboard.press('Escape');
    await page.locator(`.library-card-title[href="/en/library/${target.id}"]`).click();
    await expect(page).toHaveURL(new RegExp(`/en/library/${target.id}$`));
    const back = page.getByRole('button', { name: /^(Return to library|Back)$/i }).first();
    await back.focus(); await expect(back).toBeFocused();
    const href = page.url(), history = await page.evaluate(() => window.history.length);
    const saved = page.waitForResponse(response => response.request().method() === 'PUT' && new URL(response.url()).pathname === `/api/films/${target.id}/profile-state` && response.ok());
    trackRefresh = true;
    release();
    await saved;
    await expect.poll(async () => (await read(request, `/films/${target.id}/profile-state`)).watched).toBe(true);
    await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
    await expect(page).toHaveURL(href); await expect(back).toBeFocused();
    expect(await page.evaluate(() => window.history.length)).toBe(history);
    expect(writes).toBe(1); expect(refreshes).toHaveLength(0);
    await page.goBack(); // Exercise the cached Explore history entry, rather than the detail page's Library link.
    await expect(page).toHaveURL(exploreHref);
    const collections = page.getByRole('region', { name: en.Explore.collectionsTitle, exact: true });
    await expect(collections.getByText('Unwatched films from Germany', { exact: true })).toHaveCount(0);
    await expect(results(page)).toHaveText('59 Films');
    await expect(page.locator(`#film-link-${target.id}`).getByLabel(en.Library.watched, { exact: true })).toHaveCount(1);
    expect(writes).toBe(1);
    expect(await page.evaluate(() => window.history.length)).toBe(history);
  } finally { release(); }
});

test('empty and metadata-poor libraries keep usable search and real Film results', async ({ page, request }) => {
  await control(request, 'identity_cleanup');
  await page.goto('/en/explore');
  await expect(page.getByText(en.Explore.emptyLibrary, { exact: true })).toBeVisible();
  await expect(cards(page)).toHaveCount(0);
  await expect(page.getByRole('textbox', { name: en.Explore.searchAll, exact: true })).toBeVisible();
  await control(request, 'explore_sparse_fixture');
  await page.reload();
  await expect(page.getByText(en.Explore.collectionsFallback, { exact: true })).toBeVisible();
  await expect(cards(page)).toHaveCount(1);
  await expect(results(page)).toHaveText('1 Film');
  await page.getByRole('button', { name: 'Watched', exact: true }).click();
  await expect(page.getByRole('region', { name: en.Explore.collectionsTitle, exact: true }).getByText(en.Explore.emptyViewDetail, { exact: true })).toBeVisible();
  await expect(page.getByText(en.Explore.collectionsFallback, { exact: true })).toHaveCount(0);
});
