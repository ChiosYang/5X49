import { test, expect, type APIRequestContext, type Page, type Response } from '@playwright/test';

const backend = process.env.E2E_BACKEND!;
function gate() {
  let release!: () => void;
  const promise = new Promise<void>(resolve => { release = resolve; });
  return { promise, release };
}
async function control(request: APIRequestContext, action: string, payload: Record<string, unknown> = {}) {
  const result = await request.post(`${backend}/__e2e/control`, {
    headers: { 'x-e2e-token': process.env.E2E_TOKEN! }, data: { action, ...payload },
  });
  expect(result.ok()).toBeTruthy();
  return result.json();
}
async function inspect(page: Page, sourceId: string, candidateIndex = 0) {
  await page.goto(`/en/library/${sourceId}`);
  await page.getByRole('button', { name: 'Review match', exact: true }).click();
  await page.getByRole('button', { name: /E2E Candidate/ }).nth(candidateIndex).click();
}
function isRsc(response: Response, filmId: string) {
  return new URL(response.url()).pathname === `/en/library/${filmId}` && response.request().headers()['rsc'] === '1';
}
async function eventRefresh(page: Page, request: APIRequestContext, filmId: string) {
  const response = page.waitForResponse(r => isRsc(r, filmId));
  await control(request, 'matching_event', { film_id: filmId });
  expect((await response).ok()).toBeTruthy();
}
async function assertMatched(page: Page, filmId: string) {
  await expect(page).toHaveURL(`/en/library/${filmId}`);
  await expect(page.getByRole('heading', { name: 'E2E Candidate', exact: true, level: 1 })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Review match', exact: true })).toHaveCount(0);
  const more = page.getByRole('button', { name: 'More', exact: true });
  await expect(more).toHaveAttribute('aria-expanded', 'false');
  await more.click();
  await expect(page.getByRole('button', { name: 'Scrape metadata', exact: true })).toBeEnabled();
}
test.beforeEach(async ({ context }) => {
  await context.route('**/*', route => ['127.0.0.1', 'localhost'].includes(new URL(route.request().url()).hostname)
    ? route.continue() : route.abort('blockedbyclient'));
});

test('confirmation stays locked through event RSC identity changes, read refresh and navigation commit', async ({ page, request }) => {
  const fixture = await control(request, 'matching_fixture', { name: 'RSC race' });
  expect(fixture.source_id).not.toBe(fixture.target_id);
  await inspect(page, fixture.source_id);
  const committed = gate(), responseGate = gate(), readStarted = gate(), readGate = gate(), navigationStarted = gate(), navigationGate = gate();
  let confirmations = 0;
  let holdReads = false;
  await page.route(`**/api/films/${fixture.source_id}/scrape/confirm?*`, async route => {
    confirmations++;
    const response = await route.fetch();
    expect(response.ok()).toBeTruthy();
    expect((await response.json()).film.id).toBe(fixture.target_id);
    committed.release();
    await responseGate.promise;
    await route.fulfill({ response });
  });
  await page.route(url => url.pathname === `/api/library/films/${fixture.source_id}`, async route => {
    if (holdReads) { readStarted.release(); await readGate.promise; }
    await route.continue();
  });
  await page.route(url => url.pathname === `/en/library/${fixture.target_id}` && url.searchParams.has('_rsc'), async route => {
    navigationStarted.release();
    await navigationGate.promise;
    await route.continue();
  });
  const match = page.getByRole('button', { name: 'Review match', exact: true });
  const confirm = page.getByRole('button', { name: 'Confirm this match', exact: true });
  try {
    await confirm.click({ clickCount: 2 });
    await committed.promise;
    await eventRefresh(page, request, fixture.source_id);
    const alias = await request.get(`${backend}/library/films/${fixture.source_id}`);
    expect((await alias.json()).id).toBe(fixture.target_id);
    await expect(page.getByRole('heading', { name: 'E2E Candidate', exact: true, level: 1 })).toBeVisible();
    await expect(page).toHaveURL(`/en/library/${fixture.source_id}`);
    await expect(match).toBeDisabled();
    await expect(confirm).toBeDisabled();
    await expect(page.getByRole('button', { name: 'Favorite', exact: true })).toBeDisabled();
    // A second attempted submission after canonical RSC must also be rejected.
    await confirm.dispatchEvent('click');
    expect(confirmations).toBe(1);

    holdReads = true;
    responseGate.release();
    await readStarted.promise;
    await eventRefresh(page, request, fixture.source_id);
    await expect(match).toBeDisabled();
    await expect(page.getByRole('button', { name: 'Favorite', exact: true })).toBeDisabled();
    readGate.release();
    await navigationStarted.promise;
    await expect(page).toHaveURL(`/en/library/${fixture.source_id}`);
    await expect(match).toBeDisabled();
    await expect(page.getByRole('button', { name: 'Favorite', exact: true })).toBeDisabled();
  } finally { responseGate.release(); readGate.release(); navigationGate.release(); }
  await assertMatched(page, fixture.target_id);
  await expect(page.getByRole('button', { name: 'Favorite', exact: true })).toBeEnabled();
  expect(confirmations).toBe(1);
});

test('confirmation failure survives event RSC and can be retried once', async ({ page, request }) => {
  const fixture = await control(request, 'matching_fixture', { name: 'Retry race' });
  await inspect(page, fixture.source_id);
  const failedRequest = gate(), failureGate = gate();
  let confirmations = 0;
  await page.route(`**/api/films/${fixture.source_id}/scrape/confirm?*`, async route => {
    confirmations++;
    if (confirmations === 1) {
      failedRequest.release();
      await failureGate.promise;
      await route.fulfill({ status: 503, json: { detail: 'Synthetic confirmation failure' } });
    } else await route.continue();
  });
  const confirm = page.getByRole('button', { name: 'Confirm this match', exact: true });
  try {
    await confirm.click({ clickCount: 2 });
    await failedRequest.promise;
    await eventRefresh(page, request, fixture.source_id);
    await expect(confirm).toBeDisabled();
  } finally { failureGate.release(); }
  await expect(page.getByText('Synthetic confirmation failure', { exact: true })).toBeVisible();
  await expect(confirm).toBeEnabled();
  const unchanged = await request.get(`${backend}/library/films/${fixture.source_id}`);
  expect((await unchanged.json()).identities.tmdb).toBeFalsy();
  await confirm.click({ clickCount: 2 });
  await assertMatched(page, fixture.target_id);
  expect(confirmations).toBe(2);
});

for (const phase of ['response', 'refresh'] as const) {
  test(`leaving during ${phase} ignores late confirmation and the next Film starts unlocked`, async ({ page, request }) => {
    const fixture = await control(request, 'matching_fixture', { name: `Leave ${phase}` });
    const destination = await control(request, 'matching_fixture', { name: `Destination ${phase}` });
    await inspect(page, fixture.source_id);
    const committed = gate(), responseGate = gate(), readStarted = gate(), readGate = gate();
    let confirmations = 0;
    let lateReads = 0;
    let left = false;
    await page.route(`**/api/films/${fixture.source_id}/scrape/confirm?*`, async route => {
      confirmations++;
      const response = await route.fetch();
      expect(response.ok()).toBeTruthy();
      committed.release();
      if (phase === 'response') await responseGate.promise;
      await route.fulfill({ response });
    });
    await page.route(url => url.pathname === `/api/library/films/${fixture.source_id}`, async route => {
      if (phase === 'refresh') { readStarted.release(); await readGate.promise; }
      await route.continue();
    });
    page.on('request', r => {
      if (left && new URL(r.url()).pathname === `/api/library/films/${fixture.source_id}`) lateReads++;
    });
    try {
      await page.getByRole('button', { name: 'Confirm this match', exact: true }).click();
      await committed.promise;
      if (phase === 'refresh') await readStarted.promise;
      await page.getByRole('button', { name: 'Return to Library', exact: true }).click();
      await expect(page).toHaveURL('/en/library');
      left = true;
      await page.locator(`a[href="/en/library/${destination.source_id}"]`).first().click();
      await expect(page).toHaveURL(`/en/library/${destination.source_id}`);
      await expect(page.getByRole('button', { name: 'Review match', exact: true })).toBeEnabled();
      if (phase === 'response') {
        const lateResponse = page.waitForResponse(r => new URL(r.url()).pathname === `/api/films/${fixture.source_id}/scrape/confirm`);
        responseGate.release();
        await lateResponse;
      } else readGate.release();
      await eventRefresh(page, request, destination.source_id);
      await expect(page).toHaveURL(`/en/library/${destination.source_id}`);
      await expect(page.getByRole('button', { name: 'Review match', exact: true })).toBeEnabled();
      expect(lateReads).toBe(0);
      expect(confirmations).toBe(1);
    } finally { responseGate.release(); readGate.release(); }
  });
}

test('a saved same-Film match with failed read refresh retries reads without resubmitting', async ({ page, request }) => {
  const fixture = await control(request, 'matching_fixture', { name: 'Read retry' });
  // 900002 has no canonical Film yet: this match retains the current Film ID.
  await inspect(page, fixture.source_id, 1);
  let confirmations = 0;
  let failReads = false;
  await page.route(`**/api/films/${fixture.source_id}/scrape/confirm?*`, async route => {
    confirmations++;
    const response = await route.fetch();
    expect(response.ok()).toBeTruthy();
    expect((await response.json()).film.id).toBe(fixture.source_id);
    failReads = true;
    await route.fulfill({ response });
  });
  await page.route(url => url.pathname === `/api/library/films/${fixture.source_id}`, route => failReads
    ? route.fulfill({ status: 503, json: { detail: 'Synthetic read refresh failure' } }) : route.continue());
  await page.getByRole('button', { name: 'Confirm this match', exact: true }).click();
  const warning = page.getByText('Changes saved, but the page could not be refreshed. You do not need to save again.', { exact: true });
  await expect(warning).toBeVisible();
  const retry = page.getByRole('button', { name: 'Refresh page', exact: true });
  await expect(retry).toBeEnabled();
  failReads = false;
  await retry.click();
  await expect(warning).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Favorite', exact: true })).toBeEnabled();
  const saved = await request.get(`${backend}/library/films/${fixture.source_id}`);
  expect((await saved.json()).identities.tmdb).toBe('900002');
  expect(confirmations).toBe(1);
});
