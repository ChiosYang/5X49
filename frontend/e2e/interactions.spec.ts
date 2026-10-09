import { test, expect, type APIRequestContext, type Page } from '@playwright/test';
import { writeFile, access, mkdir } from 'node:fs/promises';
import path from 'node:path';

test.describe.configure({ mode: 'serial' });
const backend = process.env.E2E_BACKEND!;
const root = process.env.E2E_ROOT!;
let films: Array<{ id: string; title: string }>;
let retainedViewing: string;
async function control(request: APIRequestContext, action: string, payload: Record<string, unknown> = {}) {
  const r = await request.post(`${backend}/__e2e/control`, { headers: { 'x-e2e-token': process.env.E2E_TOKEN! }, data: { action, ...payload } });
  expect(r.ok()).toBeTruthy(); return r.json();
}
async function read(request: APIRequestContext, url: string) {
  const r = await request.get(`${backend}${url}`); expect(r.ok()).toBeTruthy(); return r.json();
}
async function settleWorkflow(request: APIRequestContext, id: string) {
  await expect.poll(async () => (await read(request, `/workflows/${id}`)).status, { timeout: 45000 }).toBe('succeeded');
}
test.beforeEach(async ({ context }) => {
  // Browser network is local-only too; do not silently allow third-party artwork.
  await context.route('**/*', route => {
    const url = new URL(route.request().url());
    return ['127.0.0.1', 'localhost'].includes(url.hostname) ? route.continue() : route.abort('blockedbyclient');
  });
});

test('Chinese entry points terminate on both loopback hosts', async ({ page, context, baseURL }) => {
  for (const hostname of ['127.0.0.1', 'localhost']) {
    const origin = new URL(baseURL!); origin.hostname = hostname;
    await context.addCookies([{ name: 'NEXT_LOCALE', value: 'zh', url: origin.origin }]);
    for (const pathname of ['/library', '/zh/library']) {
      const response = await page.goto(origin.origin + pathname);
      expect(response?.status()).toBe(200);
      expect(new URL(page.url()).pathname).toBe('/library');
      await expect(page.locator('html')).toHaveAttribute('lang', 'zh');
    }
  }
});

test('real empty library: invalid path, delayed save, exact scan path and refresh recovery', async ({ page, request }) => {
  expect(await read(request, '/library/films')).toEqual([]);
  await page.goto('/en/library');
  const input = page.locator('input[type=text]').first();
  await input.fill(path.join(root, 'does-not-exist'));
  await page.getByRole('button', { name: /^(Start First Scan|Scan Again)$/ }).click();
  await expect(page.getByRole('button', { name: /^(Start First Scan|Scan Again)$/ })).toBeEnabled();
  await expect(page.getByText('Media directory does not exist', { exact: true })).toBeVisible();
  expect(await read(request, '/workflows')).toEqual([]);
  await control(request, 'hold_scan');
  let saved = false;
  let scanAfterSave = false;
  await page.route(url => url.pathname === '/api/settings/media-dir', async route => {
    if (route.request().method() !== 'PUT') return route.continue();
    await new Promise(resolve => setTimeout(resolve, 500));
    const response = await route.fetch(); saved = response.ok(); await route.fulfill({ response });
  });
  page.on('request', r => { if (new URL(r.url()).pathname === '/api/library/scan') scanAfterSave = saved; });
  await input.fill(path.join(root, 'normal/media'));
  const accepted = page.waitForResponse(r => new URL(r.url()).pathname === '/api/library/scan');
  await page.getByRole('button', { name: /^(Start First Scan|Scan Again)$/ }).click();
  const response = await accepted;
  expect(response.ok()).toBeTruthy();
  expect(new URL(response.url()).searchParams.get('media_dir')).toBe(path.join(root, 'normal/media'));
  expect(scanAfterSave).toBe(true);
  const { workflow_id } = await response.json();
  await page.reload();
  await expect(page.getByRole('button', { name: /scanning/i })).toBeVisible();
  await control(request, 'release_scan');
  await settleWorkflow(request, workflow_id);
  films = await read(request, '/library/films'); expect(films).toHaveLength(12);
  const detail = await read(request, `/library/films/${films[0].id}`);
  expect(detail.primary_item.video.width).toBe(320);
  expect(detail.primary_item.video.duration_seconds).toBeGreaterThan(0);
  expect((await read(request, '/settings/media-dir')).media_dir).toBe(path.join(root, 'normal/media'));
});

test('card real mutation, explicit injected error/retry and keyboard disclosure', async ({ page, request }) => {
  await page.goto('/en/library');
  let fail = true;
  await page.route(`**/api/films/${films[0].id}/profile-state`, route => fail && route.request().method() === 'PUT'
    ? route.fulfill({ status: 503, json: { detail: 'Injected write failure' } }) : route.continue());
  await page.getByRole('button', { name: `Actions for ${films[0].title}`, exact: true }).tap();
  await page.getByRole('button', { name: 'Favorite', exact: true }).first().click();
  await expect(page.getByText('Not saved. Please try again.', { exact: true })).toBeVisible();
  expect((await read(request, `/films/${films[0].id}/profile-state`)).favorite).toBe(false);
  fail = false;
  await page.getByRole('button', { name: 'Retry', exact: true }).first().click();
  await expect.poll(async () => (await read(request, `/films/${films[0].id}/profile-state`)).favorite).toBe(true);
  await page.getByRole('button', { name: 'Filter', exact: true }).click();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button', { name: 'Filter', exact: true })).toBeFocused();
  await expect(page.getByRole('button', { name: 'Filter', exact: true })).toHaveAttribute('aria-expanded', 'false');
});

test('empty scrape feedback is specific and rejected requests are handled', async ({ page }) => {
  const pageErrors: string[] = [];
  page.on('pageerror', error => pageErrors.push(error.message));
  await page.route(`**/api/films/${films[0].id}/scrape`, route => route.fulfill({
    status: 409, json: { detail: { status: 'failed', message: 'No TMDB matches found', candidates: [] } },
  }));
  await page.goto(`/en/library/${films[0].id}`);
  await page.getByText('Film controls', { exact: true }).click();
  await page.getByRole('button', { name: 'Scrape metadata', exact: true }).click();
  await expect(page.getByText('No TMDB matches found. Check the title and year, or choose a match using a TMDB ID.', { exact: true })).toBeVisible();
  await expect(page.getByText('Film action failed', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Scrape metadata', exact: true })).toBeEnabled();
  expect(pageErrors).toEqual([]);
});

test('long unbroken and Chinese titles stay within cards and away from the year', async ({ page, request }) => {
  const title = 'InceptionQZX49NoSuchFilm'.repeat(4) + '一个非常长的中文影片标题';
  await control(request, 'set_title', { film_id: films[0].id, title });
  try {
    for (const width of [390, 1440]) {
      await page.setViewportSize({ width, height: 1050 });
      await page.goto('/en/library');
      const heading = page.getByRole('heading', { name: title, exact: true }).last();
      await expect(heading).toBeVisible();
      const bounds = await heading.evaluate(element => {
        const link = element.closest('a')!;
        const card = link.parentElement!;
        const rect = element.getBoundingClientRect();
        const year = link.lastElementChild!.getBoundingClientRect();
        const text = document.createRange(); text.selectNodeContents(element);
        return { cardRight: card.getBoundingClientRect().right, titleRight: rect.right,
          yearLeft: year.left, lines: [...text.getClientRects()].map(line => ({ left: line.left, right: line.right })),
          titleLeft: rect.left, viewportWidth: window.innerWidth, pageWidth: document.documentElement.scrollWidth };
      });
      expect(bounds.titleRight).toBeLessThanOrEqual(bounds.yearLeft);
      expect(bounds.titleRight).toBeLessThanOrEqual(bounds.cardRight);
      for (const line of bounds.lines) {
        expect(line.left).toBeGreaterThanOrEqual(bounds.titleLeft - 1);
        expect(line.right).toBeLessThanOrEqual(bounds.titleRight + 1);
      }
      expect(bounds.pageWidth).toBeLessThanOrEqual(bounds.viewportWidth);
    }
  } finally {
    await control(request, 'set_title', { film_id: films[0].id, title: films[0].title });
  }
});

async function confirmAsk(page: Page) {
  await page.getByRole('button', { name: 'Review conditions', exact: true }).click();
  await page.getByRole('button', { name: 'Find films with these conditions', exact: true }).click();
}
test('no-key real facts, zero results require reconfirmation; detail reload restores Ask', async ({ page, request }) => {
  expect((await read(request, '/ask/status')).configured).toBe(false);
  await page.goto('/en/ask');
  await expect(page.getByRole('button', { name: 'Use filters', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('button', { name: 'Choose Genre', exact: true }).click();
  const drama = page.getByRole('button', { name: /Drama/ }).first(); await drama.focus(); await page.keyboard.press('Enter');
  await page.getByPlaceholder('Japan or JP').fill('JP');
  await confirmAsk(page);
  await page.getByRole('button', { name: 'Remove Genre', exact: true }).click();
  await expect(page.getByPlaceholder('Japan or JP')).toHaveValue('JP');
  await expect(page.getByRole('button', { name: 'Find films with these conditions', exact: true })).toHaveCount(0);
  await confirmAsk(page);
  await expect(page.locator('a[href*="/library/film_"]').first()).toBeVisible();
  const saved = await page.evaluate(() => sessionStorage.getItem('5x49.ask.confirmed.v1'));
  expect(saved).not.toContain('question');
  await page.locator('a[href*="/library/film_"]').first().click();
  await page.getByRole('button', { name: 'Watched today', exact: true }).waitFor();
  await page.reload();
  await page.getByRole('button', { name: /^Return to library$/i }).click();
  await expect(page).toHaveURL(/\/en\/ask$/);
  await expect(page.getByPlaceholder('Japan or JP')).toHaveValue('JP');
  await expect(page.locator('a[href*="/library/film_"]').first()).toBeVisible();
});

test('filtered Library detail return preserves URL, focus and scroll', async ({ page }) => {
  await page.goto('/en/library?filter=unwatched&sort=title');
  const card = page.locator('a[id^="film-link-"]').nth(4);
  await card.scrollIntoViewIfNeeded();
  const id = await card.getAttribute('id');
  await card.click();
  await page.getByRole('button', { name: 'Watched today', exact: true }).waitFor();
  await page.getByRole('button', { name: /^(Return to library|Back)$/i }).click();
  await expect(page).toHaveURL(/filter=unwatched&sort=title/);
  await expect(page.locator(`#${id}`)).toBeFocused();
  const expected = await page.evaluate(() => JSON.parse(sessionStorage.getItem('5x49:return-context:v1')!).scrollY);
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeCloseTo(expected, -1);
});

test('real Viewing exact undo and committed POST with injected failed GET, retry is read-only', async ({ page, request }) => {
  const film = films[0];
  const today = new Date().toLocaleDateString('en-CA');
  const original = await request.post(`${backend}/films/${film.id}/viewings`, { data: { watched_at: today } });
  expect(original.ok()).toBeTruthy(); retainedViewing = (await original.json()).id;
  await page.goto(`/en/library/${film.id}`);
  let failRead = false, posts = 0;
  await page.route(`**/api/films/${film.id}/viewings`, async route => {
    if (route.request().method() === 'POST') { posts++; failRead = true; return route.continue(); }
    return failRead ? route.fulfill({ status: 500, json: { detail: 'Injected post-commit read failure' } }) : route.continue();
  });
  await page.getByRole('button', { name: 'Watched today', exact: true }).click();
  await expect(page.getByText('Changes saved, but the list could not be refreshed. Do not save again.', { exact: true })).toBeVisible();
  expect(await read(request, `/films/${film.id}/viewings`)).toHaveLength(2);
  failRead = false;
  await page.getByRole('button', { name: 'Refresh list', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Refresh list', exact: true })).toHaveCount(0);
  expect(posts).toBe(1);
  await page.getByRole('button', { name: 'Undo this new record', exact: true }).click();
  await expect.poll(async () => (await read(request, `/films/${film.id}/viewings`)).map((v: {id:string}) => v.id)).toEqual([retainedViewing]);
});

test('generated abnormal media and TMDB transport fixture: inspect/skip/confirm uses real persistence', async ({ page, request }) => {
  const scan = await request.post(`${backend}/library/scan?media_dir=${encodeURIComponent(path.join(root, 'mixed/media'))}`);
  expect(scan.ok()).toBeTruthy(); await settleWorkflow(request, (await scan.json()).workflow_id);
  const pending = (await read(request, '/library/films')).filter((f: {primary_item: {metadata: {scrape_status: string}}}) => f.primary_item.metadata.scrape_status === 'pending');
  expect(pending.length).toBeGreaterThanOrEqual(2);
  for (const film of pending.slice(0, 2)) {
    const scrape = await request.post(`${backend}/films/${film.id}/scrape`, { data: {} });
    expect(scrape.ok()).toBeTruthy(); expect((await scrape.json()).status).toBe('needs_review');
  }
  await page.goto('/en/library?view=metadata');
  await expect(page.getByText(/Awaiting confirmation/).first()).toBeVisible();
  await expect(page.getByText('Previous attempt failed', { exact: true })).toHaveCount(0);
  const beforeReview = await read(request, '/library/films');
  let confirmations = 0;
  page.on('request', r => { if (r.method() === 'POST' && new URL(r.url()).pathname.endsWith('/scrape/confirm')) confirmations++; });
  await page.getByRole('button', { name: /E2E Candidate/ }).first().click();
  await expect(page.getByText('Fixture synopsis for explicit comparison.', { exact: true })).toBeVisible();
  expect(confirmations).toBe(0);
  expect(await read(request, '/library/films')).toEqual(beforeReview);
  await page.getByRole('button', { name: 'Skip for now', exact: true }).click();
  await expect(page.getByText(/1 skipped films/)).toBeVisible();
  await page.getByRole('textbox').first().press('Enter');
  await page.getByRole('button', { name: /E2E Candidate/ }).first().click();
  const confirmation = page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname.endsWith('/scrape/confirm'));
  await page.getByRole('button', { name: 'Confirm this match', exact: true }).click();
  const response = await confirmation; expect(response.ok()).toBeTruthy(); expect(confirmations).toBe(1);
  const matchedId = new URL(response.url()).pathname.split('/')[3];
  const result = await read(request, `/library/films/${matchedId}`);
  expect(result.title).toBe('E2E Candidate');
  await page.getByRole('button', { name: 'Revisit skipped films', exact: true }).click();
  await expect(page.getByRole('button', { name: /E2E Candidate/ }).first()).toBeVisible();
});

test('nine real queued workflows, cancel failure, actual cancellation and retry', async ({ page, request }) => {
  await control(request, 'tasks');
  await page.goto('/en/library');
  await page.getByRole('button', { name: 'Background workflows', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Cancel workflow', exact: true })).toHaveCount(9);
  let fail = true;
  await page.route('**/api/workflows/*/cancel', route => fail ? route.fulfill({ status: 503, json: { detail: 'Injected cancellation failure' } }) : route.continue());
  await page.getByRole('button', { name: 'Cancel workflow', exact: true }).first().click();
  await expect(page.getByText('Cancellation failed.', { exact: false })).toBeVisible();
  fail = false;
  await page.getByRole('button', { name: 'Cancel workflow', exact: true }).first().click();
  await expect(page.getByRole('button', { name: 'Cancel workflow', exact: true })).toHaveCount(8);
  let failRetry = true;
  await page.route('**/api/workflows/*/retry', route => failRetry ? route.fulfill({ status: 503, json: { detail: 'Injected retry failure' } }) : route.continue());
  await page.getByRole('button', { name: 'Retry workflow', exact: true }).first().click();
  await expect(page.getByText('Retry request failed. Try again.', { exact: true })).toBeVisible();
  failRetry = false;
  await page.getByRole('button', { name: 'Retry workflow', exact: true }).first().click();
  await expect(page.getByRole('button', { name: 'Cancel workflow', exact: true })).toHaveCount(9);
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button', { name: 'Background workflows', exact: true })).toBeFocused();
  for (const w of await read(request, '/workflows?include_active=true')) if (['queued', 'running'].includes(w.status))
    expect((await request.post(`${backend}/workflows/${w.id}/cancel`)).ok()).toBeTruthy();
  await control(request, 'resume_tasks');
});

test('real process restart persists records; Chinese narrow-screen primary flow', async ({ page, request }) => {
  const before = await read(request, '/library/films');
  await writeFile(path.join(root, 'restart'), 'requested');
  await expect.poll(async () => { try { await access(path.join(root, 'restarted')); return true; } catch { return false; } }, { timeout: 30000 }).toBe(true);
  expect((await read(request, '/library/films')).map((f: {id:string}) => f.id)).toEqual(before.map((f: {id:string}) => f.id));
  expect((await read(request, `/films/${films[0].id}/viewings`)).map((v: {id:string}) => v.id)).toEqual([retainedViewing]);
  expect((await read(request, `/films/${films[0].id}/profile-state`)).favorite).toBe(true);
  await page.context().setExtraHTTPHeaders({ 'Accept-Language': 'zh-CN' });
  await page.context().addCookies([{ name: 'NEXT_LOCALE', value: 'zh', url: process.env.E2E_BASE_URL! }]);
  await page.goto('/ask');
  await expect(page.getByRole('button', { name: '使用条件表单', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '确认筛选条件', exact: true }).click();
  await page.getByRole('button', { name: '按这些条件查找', exact: true }).click();
  await expect(page.locator('a[href*="/library/film_"]').first()).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test('detail operations consume failures and saved-read retry never replays a write', async ({ page, request }) => {
  const film = (await read(request, '/library/films'))[0];
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(`/en/library/${film.id}`);
  const state = await read(request, `/films/${film.id}/profile-state`);
  const favorite = () => page.getByRole('button',{name:state.favorite ? 'Remove favorite' : 'Favorite',exact:true});
  let rejectWrite = true, rejectRead = false, writes = 0;
  await page.route(`**/api/films/${film.id}/profile-state`, route => {
    if (route.request().method() !== 'PUT') return route.continue();
    writes++;
    return rejectWrite ? route.fulfill({status:503,json:{detail:'Test write failure'}}) : route.continue();
  });
  await favorite().click();
  await expect(page.getByText('Your favorite or watched change was not saved. The service is unavailable. Try again later.',{exact:true})).toBeVisible();
  expect((await read(request,`/films/${film.id}/profile-state`)).favorite).toBe(state.favorite);
  rejectWrite=false;rejectRead=true;
  await page.route(`**/api/library/films/${film.id}`, route => rejectRead ? route.fulfill({status:503,json:{detail:'Test read failure'}}) : route.continue());
  await favorite().click();
  await expect(page.getByText('Changes saved, but the page could not be refreshed. You do not need to save again.',{exact:true})).toBeVisible();
  expect((await read(request,`/films/${film.id}/profile-state`)).favorite).toBe(!state.favorite);
  rejectRead=false;
  await page.getByRole('button',{name:'Refresh page',exact:true}).click();
  await expect(page.getByRole('button',{name:'Refresh page',exact:true})).toHaveCount(0);
  expect(writes).toBe(2);
  for (const [label,endpoint,prefix] of [
    ['Refresh external scores',`/api/films/${film.id}/external-scores/refresh`,'The score refresh could not be started.'],
    ['Refresh primary edition',`/api/library/items/${film.primary_item.id}/refresh`,'The edition refresh could not be started.'],
    ['Ignore primary edition',`/api/library/items/${film.primary_item.id}/ignore`,'The edition was not ignored.'],
  ]) {
    await page.route(url => url.pathname===endpoint,route => route.fulfill({status:503,json:{detail:'Test operation failure'}}));
    await page.getByRole('button',{name:label,exact:true}).click();
    await expect(page.getByText(`${prefix} The service is unavailable. Try again later.`,{exact:true})).toBeVisible();
  }
  expect(errors).toEqual([]);
});

test('same-directory editions expose stable default selection and mobile title wrapping', async ({ page, request }) => {
  const folder=path.join(root,'normal/media/Core.Quality.1967');
  await mkdir(folder,{recursive:true});
  await writeFile(path.join(folder,'Core.Quality.1967.Cut.A.mkv'),'edition A');
  await writeFile(path.join(folder,'Core.Quality.1967.Cut.B.mp4'),'edition B');
  await writeFile(path.join(folder,'Core.Quality.1967.trailer.mkv'),'extra');
  const title='UnbrokenTitle'.repeat(7);
  await writeFile(path.join(folder,'movie.nfo'),`<movie><title>${title}</title><year>1967</year><tmdbid>5511</tmdbid></movie>`);
  const scan=await request.post(`${backend}/library/scan-folder?folder_path=${encodeURIComponent(folder)}`);
  expect(scan.ok()).toBeTruthy();await settleWorkflow(request,(await scan.json()).workflow_id);
  const film=(await read(request,'/library/films')).find((item:{title:string})=>item.title===title);
  const before=await read(request,`/library/films/${film.id}`);
  expect(before.editions).toHaveLength(2);
  await page.goto(`/en/library/${film.id}`);
  await page.getByRole('button',{name:'Use as default edition',exact:true}).click();
  await expect.poll(async()=> (await read(request,`/library/films/${film.id}`)).primary_item.id).not.toBe(before.primary_item.id);
  const selected=(await read(request,`/library/films/${film.id}`)).primary_item.id;
  const repeat=await request.post(`${backend}/library/scan-folder?folder_path=${encodeURIComponent(folder)}`);
  await settleWorkflow(request,(await repeat.json()).workflow_id);
  expect((await read(request,`/library/films/${film.id}`)).primary_item.id).toBe(selected);
  expect(await page.locator('h1').first().evaluate(node=>node.scrollWidth<=node.clientWidth)).toBe(true);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('navigation traps focus, closes with Escape and production diagnostics are usable', async ({ page }) => {
  await page.goto('/en/library');
  const menu=page.getByRole('button',{name:'Menu',exact:true});
  await menu.click();
  const dialog=page.getByRole('dialog',{name:'Menu',exact:true});
  await expect(dialog).toBeVisible();
  await expect(dialog.locator('a[href="#"]')).toHaveCount(0);
  await dialog.getByRole('link').last().focus();
  await page.keyboard.press('Tab');
  await expect(dialog.getByRole('button',{name:'Close',exact:true})).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(menu).toBeFocused();await expect(menu).toHaveAttribute('aria-expanded','false');
  await page.goto('/en/settings?section=maintenance');
  await expect(page.getByRole('heading',{name:'System diagnostics',exact:true})).toBeVisible();
  await expect(page.getByRole('heading',{name:'Backup and recovery',exact:true})).toBeVisible();
  await expect(page.getByText('Full database restore requires the application to be stopped',{exact:true})).toBeVisible();
});
