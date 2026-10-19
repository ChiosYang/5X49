import { test, expect, type APIRequestContext, type Page } from '@playwright/test';
import path from 'node:path';

const backend = process.env.E2E_BACKEND!;
const cards = (page: Page) => page.locator('a[id^="film-link-"]');
const titles = (page: Page) => cards(page).locator('h2,h3').allTextContents();
async function control(request: APIRequestContext, action: string, extra = {}) {
  const response = await request.post(`${backend}/__e2e/control`, { headers: { 'x-e2e-token': process.env.E2E_TOKEN! }, data: { action, ...extra } });
  expect(response.ok()).toBeTruthy(); return response.json();
}
async function describe(page: Page, question: string) {
  await page.getByLabel('Your question', { exact: true }).fill(question);
  await expect(page.getByLabel('Your question', { exact: true })).toHaveValue(question);
  await page.getByRole('checkbox', { name: /^Send this question/ }).check();
  await page.getByRole('button', { name: 'Send and review conditions', exact: true }).click();
}
async function confirm(page: Page) {
  await page.getByRole('button', { name: 'Find films with these conditions', exact: true }).click();
}
async function preview(page: Page) {
  await page.getByRole('button', { name: 'Review conditions', exact: true }).click();
}

test.beforeAll(async ({ request }) => { await control(request, 'identity_cleanup'); await control(request, 'ask_fixture'); });
test.afterAll(async ({ request }) => { await control(request, 'ask_mode', { mode: 'no_key' }); await control(request, 'ask_cleanup'); });
test.beforeEach(async ({ context, request }) => {
  await control(request, 'ask_mode', { mode: 'fixture' });
  await control(request, 'ask_disclosure', { model:'offline/fixture-v1', host:'fixture.local' });
  await context.route('**/*', route => ['127.0.0.1', 'localhost'].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort('blockedbyclient'));
});

test('Explore interprets, exposes editable conditions and queries only after confirmation', async ({ page }) => {
  let queries = 0;
  page.on('request', request => { if (new URL(request.url()).pathname === '/api/ask/query') queries += 1; });
  await page.goto('/en/explore');
  await page.getByLabel('Your question', { exact: true }).fill('Films no longer than 90 minutes.');
  await expect(page.getByRole('button', { name: 'Send and review conditions', exact: true })).toBeDisabled();
  await page.getByRole('checkbox', { name: /^Send this question/ }).check();
  await page.getByRole('button', { name: 'Send and review conditions', exact: true }).click();
  await expect(page.getByLabel('Maximum duration (minutes)', { exact: true })).toHaveValue('90');
  await expect(page.getByRole('region', { name: 'Review conditions' })).toContainText('Duration ≤ 90 min');
  expect(queries).toBe(0); await expect(cards(page)).toHaveCount(0);
  await page.getByLabel('Maximum duration (minutes)', { exact: true }).fill('91');
  await expect(page.getByRole('button', { name: 'Find films with these conditions', exact: true })).toHaveCount(0);
  await preview(page); expect(queries).toBe(0);
  await confirm(page); await expect.poll(() => titles(page)).toEqual(['Alpha', 'Beta']);
  await expect(page.getByText('5401 seconds (Measured primary video)', { exact: false })).toBeVisible();
  expect(queries).toBe(1);
});

test('numeric boundary, personal stars, roles and watched state match real local facts', async ({ page }) => {
  await page.goto('/en/explore');
  await describe(page, '找九十年代 Shared Person 导演的日本动作片，我的总体评分三到五星，时长至少90分钟，按年份升序。');
  await expect(page.getByLabel('Person', { exact: true })).toHaveValue('Shared Person');
  await confirm(page); await expect.poll(() => titles(page)).toEqual(['Alpha']);
  const results = page.getByRole('region', { name: 'Search results' });
  await expect(results).toContainText('3/5 stars'); await expect(results).toContainText('5400 seconds');
  // Hold application frames so the editor's deferred focus runs only after
  // the next field interaction, reproducing the CI-discovered focus race.
  await page.evaluate(() => {
    const original = window.requestAnimationFrame;
    const pending: FrameRequestCallback[] = [];
    window.requestAnimationFrame = callback => { pending.push(callback); return -pending.length; };
    (window as typeof window & { releaseAskFrames?: () => void }).releaseAskFrames = () => {
      window.requestAnimationFrame = original;
      pending.forEach(callback => original.call(window, callback));
    };
  });
  try {
    await page.getByRole('button', { name: 'Edit conditions', exact: true }).click();
    await page.getByLabel('Minimum duration (minutes)', { exact: true }).fill('90');
    await page.getByLabel('Include the minimum duration', { exact: true }).uncheck();
  } finally {
    await page.evaluate(() => {
      const state = window as typeof window & { releaseAskFrames?: () => void };
      state.releaseAskFrames?.(); delete state.releaseAskFrames;
    });
  }
  await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
  await expect(page.getByLabel('Include the minimum duration', { exact: true })).toBeFocused();
  await expect(page.getByLabel('Genre', { exact: true })).toHaveValue('Action');
  await preview(page); await confirm(page); await expect(page.getByText('No films satisfy all these conditions.', { exact: false })).toBeVisible();
});

test('zero matches offer relaxation only as an editable unconfirmed draft', async ({ page }) => {
  let queries = 0;
  page.on('request', request => { if (request.url().endsWith('/ask/query')) queries += 1; });
  await page.goto('/en/explore'); await describe(page, 'German films from the 1990s.'); await confirm(page);
  await expect(page.getByText('No films satisfy all these conditions.', { exact: false })).toBeVisible();
  await page.getByRole('button', { name: 'Remove Country', exact: true }).click();
  await expect(page.getByLabel('Country', { exact: true })).toHaveValue('');
  await expect(page.getByLabel('Release decade', { exact: true })).toHaveValue('1990');
  expect(queries).toBe(1); await expect(cards(page)).toHaveCount(0);
  await preview(page); expect(queries).toBe(1); await confirm(page);
  await expect.poll(() => titles(page)).toEqual(['Alpha', 'Beta']);
});

test('fuzzy person identity requires explicit choice before query and enforces actor role', async ({ page }) => {
  await page.goto('/en/explore'); await describe(page, 'Films involving Shared.');
  await expect(page.getByRole('button', { name: 'Find films with these conditions', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: /^Shared Person.*Alpha/ }).click();
  await page.getByLabel("Person's role", { exact: true }).selectOption('actor');
  await preview(page); await confirm(page); await expect.poll(() => titles(page)).toEqual(['Beta']);
});

test('unsupported negation and taste requests cannot prepare a partial query', async ({ page }) => {
  for (const question of ['Japanese films, excluding horror.', '推荐符合我口味的温暖治愈电影。']) {
    await page.goto('/en/explore'); await describe(page, question);
    await expect(page.getByRole('region', { name: 'Review conditions' })).toContainText('No partial search was prepared');
    await expect(page.getByRole('button', { name: 'Find films with these conditions', exact: true })).toHaveCount(0);
    await expect(cards(page)).toHaveCount(0);
  }
});

test('provider failure retries explicitly and manual filters remain available', async ({ page, request }) => {
  await control(request, 'ask_mode', { mode: 'timeout_once' });
  await page.goto('/en/explore'); await describe(page, 'Find Japanese films.');
  await expect(page.getByRole('region', { name: 'AI Film finder' }).getByRole('alert')).toContainText('The model timed out');
  await page.getByRole('button', { name: 'Retry', exact: true }).click();
  await expect(page.getByLabel('Country', { exact: true })).toHaveValue('JP');
  await confirm(page); await expect(cards(page)).toHaveCount(2);
});

test('no-key fallback performs the entire local confirmation flow without interpreting', async ({ page, request }) => {
  await control(request, 'ask_mode', { mode: 'no_key' });
  let interprets = 0;
  page.on('request', request => { if (request.url().endsWith('/ask/interpret')) interprets += 1; });
  await page.goto('/en/explore');
  await page.getByRole('button', { name: 'Use filters', exact: true }).click();
  await expect(page.getByText('No model key is configured.', { exact: false })).toBeVisible();
  await page.getByLabel('Minimum Film personal overall rating', { exact: true }).fill('4');
  await preview(page); await confirm(page); await expect.poll(() => titles(page)).toEqual(['Beta']);
  expect(interprets).toBe(0);
});

test('cancel suppresses a delayed response and does not persist an unconfirmed plan', async ({ page }) => {
  let release!: () => void, reached!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  const waiting = new Promise<void>(resolve => { reached = resolve; });
  await page.route('**/api/ask/interpret', async route => { const response = await route.fetch(); reached(); await gate; await route.fulfill({ response }).catch(() => {}); });
  await page.goto('/en/explore'); await describe(page, 'Find Japanese films.'); await waiting;
  await page.getByRole('button', { name: 'Cancel request', exact: true }).click(); release();
  await expect(page.getByLabel('Your question', { exact: true })).toHaveValue('');
  await expect(page.getByRole('region', { name: 'Review conditions' })).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => Object.keys(sessionStorage).filter(key => key.startsWith('5x49.ask.confirmed.v2.explore.')))).toEqual([]);
});

test('a delayed earlier interpretation cannot replace a newer request', async ({ page }) => {
  let release!: () => void, reached!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  const waiting = new Promise<void>(resolve => { reached = resolve; });
  await page.route('**/api/ask/interpret', async route => {
    if (route.request().postDataJSON().question !== 'Find Japanese films.') return route.continue();
    const response = await route.fetch(); reached(); await gate; await route.fulfill({ response }).catch(() => {});
  });
  await page.goto('/en/explore'); await describe(page, 'Find Japanese films.'); await waiting;
  await describe(page, 'Films no longer than 90 minutes.');
  await expect(page.getByLabel('Maximum duration (minutes)', { exact: true })).toHaveValue('90'); release();
  await confirm(page); await expect.poll(() => titles(page)).toEqual(['Alpha']);
  await expect(page.getByLabel('Country', { exact: true })).toHaveValue('');
});

test('changing a plan during a delayed query suppresses its old results', async ({ page }) => {
  let release!: () => void, reached!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  const waiting = new Promise<void>(resolve => { reached = resolve; });
  let first = true;
  await page.route('**/api/ask/query', async route => {
    if (!first) return route.continue(); first = false;
    const response = await route.fetch(); reached(); await gate; await route.fulfill({ response }).catch(() => {});
  });
  await page.goto('/en/explore'); await describe(page, 'Find Japanese films.'); await confirm(page); await waiting;
  await page.getByLabel('Minimum Film personal overall rating', { exact: true }).fill('5');
  await preview(page); await confirm(page); await expect.poll(() => titles(page)).toEqual(['Beta']); release();
  await expect.poll(() => titles(page)).toEqual(['Beta']);
});

test('return from a Film restores only the previously confirmed local query', async ({ page }) => {
  await page.goto('/en/explore'); await describe(page, 'Films no longer than 90 minutes.'); await confirm(page);
  await expect(cards(page)).toHaveCount(1); await cards(page).first().click();
  await expect(page).toHaveURL(/\/en\/library\/film_/);
  await page.goBack(); await expect.poll(() => titles(page)).toEqual(['Alpha']);
  const stored = await page.evaluate(() => Object.entries(sessionStorage).find(([key]) => key.startsWith('5x49.ask.confirmed.v2.explore.'))?.[1] ?? null);
  expect(stored).not.toContain('question'); expect(stored).not.toContain('results');
  await page.getByRole('button', { name: 'Return to factual Explore', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Search results' })).toHaveCount(0);
});

test('desktop and narrow Chinese preserve editorial title, navigation and factual reasons', async ({ page }) => {
  const errors: string[] = []; page.on('pageerror', error => errors.push(error.message));
  await page.setViewportSize({ width: 1440, height: 1000 }); await page.goto('/zh/explore');
  await page.getByLabel('你的问题', { exact: true }).fill('找我的影片总体评分至少四星的电影。');
  await page.getByRole('checkbox', { name: /^将此问题/ }).check();
  await page.getByRole('button', { name: '发送并核对条件', exact: true }).click();
  await page.getByRole('button', { name: '按这些条件查找', exact: true }).click();
  await expect(cards(page)).toHaveCount(1); await expect(page.locator('h1')).toHaveClass(/font-serif.*text-5xl/);
  await page.screenshot({ path: path.join('e2e-artifacts','ask-desktop-zh.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await expect(page.getByText('5/5 星', { exact: false })).toBeVisible();
  await page.screenshot({ path: path.join('e2e-artifacts','ask-narrow-zh.png'), fullPage: true });
  expect(errors).toEqual([]);
});

test('invalid edited ranges and malicious provider formats fail without a local query', async ({ page }) => {
  let queries=0;
  page.on('request', request => { if (request.url().endsWith('/ask/query')) queries+=1; });
  await page.goto('/en/explore'); await page.getByRole('button',{name:'Use filters',exact:true}).click();
  await page.getByLabel('Minimum duration (minutes)',{exact:true}).fill('120');
  await page.getByLabel('Maximum duration (minutes)',{exact:true}).fill('90');
  await preview(page);
  await expect(page.getByRole('region',{name:'AI Film finder'}).getByRole('alert')).toContainText('Check the conditions');
  expect(queries).toBe(0);
  await page.getByRole('button',{name:'Describe a film search',exact:true}).click();
  await describe(page,'Show films.');
  await expect(page.getByRole('region',{name:'AI Film finder'}).getByRole('alert')).toContainText('The model returned an invalid plan');
  expect(queries).toBe(0);
  await expect(page.getByRole('button',{name:'Find films with these conditions',exact:true})).toHaveCount(0);
});

test('withdrawing consent disables interpretation retry until explicitly approved again', async ({ page, request }) => {
  await control(request,'ask_mode',{mode:'timeout_once'});
  let interpretations=0;
  page.on('request', req=>{ if(req.url().endsWith('/ask/interpret')) interpretations+=1; });
  await page.goto('/en/explore'); await describe(page,'Find Japanese films.');
  await expect(page.getByRole('region',{name:'AI Film finder'}).getByRole('alert')).toContainText('The model timed out');
  await page.getByRole('checkbox',{name:/^Send this question/}).uncheck();
  await expect(page.getByRole('button',{name:'Retry',exact:true})).toBeDisabled();
  expect(interpretations).toBe(1);
  await page.getByRole('checkbox',{name:/^Send this question/}).check();
  await page.getByRole('button',{name:'Retry',exact:true}).click();
  await expect(page.getByLabel('Country',{exact:true})).toHaveValue('JP');
  expect(interpretations).toBe(2);
});

test('SWR target disclosure updates revoke prior consent and retry binds the new target', async ({ page, request }) => {
  await control(request,'ask_mode',{mode:'timeout_once'});
  const payloads: Array<Record<string, unknown>>=[];
  page.on('request', req=>{ if(req.url().endsWith('/ask/interpret')) payloads.push(req.postDataJSON()); });
  await page.goto('/en/explore'); await describe(page,'Find Japanese films.');
  await expect(page.getByRole('region',{name:'AI Film finder'}).getByRole('alert')).toContainText('The model timed out');
  const target=await control(request,'ask_disclosure',{model:'offline/fixture-v2',host:'other.fixture.local'});
  await page.evaluate(()=>window.dispatchEvent(new Event('focus')));
  const consent=page.getByRole('checkbox',{name:/^Send this question.*other\.fixture\.local/});
  await expect(consent).not.toBeChecked();
  await expect(page.getByRole('button',{name:'Retry',exact:true})).toBeDisabled();
  expect(payloads).toHaveLength(1);
  await consent.check(); await page.getByRole('button',{name:'Retry',exact:true}).click();
  await expect(page.getByLabel('Country',{exact:true})).toHaveValue('JP');
  expect(payloads[1].provider_disclosure).toBe(target.disclosure_id);
  expect(payloads[0].provider_disclosure).not.toBe(target.disclosure_id);
});

test('a target changed after disclosure is rejected by the real backend before interpretation', async ({ page, request }) => {
  await control(request,'ask_mode',{mode:'timeout_once'});
  await page.goto('/en/explore'); await describe(page,'Find Japanese films.');
  await expect(page.getByRole('region',{name:'AI Film finder'}).getByRole('alert')).toContainText('The model timed out');
  await control(request,'ask_disclosure',{model:'offline/fixture-v2',host:'other.fixture.local'});
  const rejected=page.waitForResponse(response=>response.url().endsWith('/ask/interpret')&&response.status()===409);
  await page.getByRole('button',{name:'Retry',exact:true}).click(); await rejected;
  await expect(page.getByRole('region',{name:'AI Film finder'}).getByRole('alert')).toContainText('The provider or model changed');
  await expect(page.getByRole('checkbox',{name:/^Send this question/})).not.toBeChecked();
  await expect(page.getByRole('button',{name:'Retry',exact:true})).toBeDisabled();
  await page.getByRole('checkbox',{name:/^Send this question.*other\.fixture\.local/}).check();
  await page.getByRole('button',{name:'Retry',exact:true}).click();
  await expect(page.getByLabel('Country',{exact:true})).toHaveValue('JP');
});

test('Film person Explore deep link cannot restore an AI plan from a different source query', async ({ page }) => {
  await page.goto('/en/explore'); await describe(page,'Films no longer than 90 minutes.'); await confirm(page);
  await expect.poll(()=>titles(page)).toEqual(['Alpha']); await cards(page).first().click();
  await expect(page).toHaveURL(/\/en\/library\/film_/);
  const personLink=page.locator('a[href*="/explore?person="]').first();
  await personLink.click(); await expect(page).toHaveURL(/\/explore\?person=/);
  await expect.poll(()=>titles(page)).toEqual(['Alpha','Beta']);
  await expect(page.getByRole('region',{name:'Review conditions'})).toHaveCount(0);
  await expect(page.getByLabel('Your question',{exact:true})).toHaveValue('');
});

test('Back and Forward restore only the confirmed plan for the normalized query and history entry', async ({ page }) => {
  await page.goto('/en/explore'); await describe(page,'Films no longer than 90 minutes.'); await confirm(page);
  await expect.poll(()=>titles(page)).toEqual(['Alpha']);
  await page.goto('/en/explore?country=JP'); await expect.poll(()=>titles(page)).toEqual(['Alpha','Beta']);
  await expect(page.getByRole('region',{name:'Review conditions'})).toHaveCount(0);
  await page.goBack(); await expect(page).toHaveURL(/\/en\/explore$/); await expect.poll(()=>titles(page)).toEqual(['Alpha']);
  await page.goForward(); await expect(page).toHaveURL(/country=JP/); await expect.poll(()=>titles(page)).toEqual(['Alpha','Beta']);
  await expect(page.getByRole('region',{name:'Review conditions'})).toHaveCount(0);
});

test('a fresh Explore entry from Film does not inherit an older same-URL AI confirmation', async ({ page }) => {
  await page.goto('/en/explore'); await describe(page,'Films no longer than 90 minutes.'); await confirm(page);
  await expect.poll(()=>titles(page)).toEqual(['Alpha']); await cards(page).first().click();
  await expect(page).toHaveURL(/\/en\/library\/film_/);
  await page.goto('/en/explore'); await expect(cards(page)).toHaveCount(0);
  await expect(page.getByRole('region',{name:'Review conditions'})).toHaveCount(0);
  await page.goBack(); await expect(page).toHaveURL(/\/en\/library\/film_/);
  await page.goBack(); await expect.poll(()=>titles(page)).toEqual(['Alpha']);
});


test('explicit English quantities remain editable and unqueried until confirmed', async ({ page }) => {
  let queries=0;
  page.on('request', req=>{ if(req.url().endsWith('/ask/query')) queries+=1; });
  const cases = [
    ['Films an hour or less.','Maximum duration (minutes)','60'],
    ['Films shorter than twenty minutes.','Maximum duration (minutes)','20'],
    ['Films forty-five minutes or less.','Maximum duration (minutes)','45'],
    ['Films shorter than one hundred and twenty minutes.','Maximum duration (minutes)','120'],
    ['Films an hour and a half or less.','Maximum duration (minutes)','90'],
    ['Films 1.5 hrs or more.','Minimum duration (minutes)','90'],
  ];
  for (const [question,label,value] of cases) {
    await page.goto('/en/explore'); await describe(page,question);
    await expect(page.getByLabel(label,{exact:true})).toHaveValue(value);
    await expect(page.getByRole('button',{name:'Find films with these conditions',exact:true})).toBeVisible();
    expect(queries).toBe(0);
  }
});


test('initial Explore hydration keeps the composer unavailable until recovery is ready', async ({ page }) => {
  let release!: () => void;
  const hydration = new Promise<void>(resolve => { release=resolve; });
  await page.route(/\/_next\/static\/.*\.js(?:\?|$)/, async route => { await hydration; await route.continue(); });
  try {
    await page.goto('/en/explore',{waitUntil:'commit'});
    await expect(page.getByLabel('Your question',{exact:true})).toBeDisabled();
  } finally { release(); }
  await expect(page.getByLabel('Your question',{exact:true})).toBeEnabled();
  await describe(page,'Films an hour or less.');
  await expect(page.getByLabel('Maximum duration (minutes)',{exact:true})).toHaveValue('60');
});
