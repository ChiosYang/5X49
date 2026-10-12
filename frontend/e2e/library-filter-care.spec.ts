import { test, expect, type APIRequestContext, type Page } from '@playwright/test';
import path from 'node:path';

const backend = process.env.E2E_BACKEND!;
const applied = new URLSearchParams({sort:'title',dir:'desc',filter:'watched',q:'Shelf',favorite:'true',
  duration_min:'80',duration_max:'80',rating_min:'3',rating_max:'3',year_min:'1980',year_max:'1980',page:'2'});
const filmsUrl = `/en/library?${applied}`;
const cards = (page: Page) => page.locator('a[id^="film-link-"]');

async function control(request: APIRequestContext, action: string, mode?: string) {
  const response = await request.post(`${backend}/__e2e/control`, {
    headers: {'x-e2e-token':process.env.E2E_TOKEN!}, data:{action,mode} });
  expect(response.ok()).toBeTruthy();
  return response.json();
}

async function expectFilmsRestored(page: Page) {
  await expect(page).toHaveURL(filmsUrl);
  await expect(cards(page).locator('h2,h3')).toHaveText(['Shelf 01','Shelf 00']);
  await expect(page.getByRole('searchbox', {name:'Search library',exact:true})).toHaveValue('Shelf');
  await expect(page.getByLabel('Watched status',{exact:true})).toHaveValue('watched');
  await expect(page.getByLabel('Favorites only',{exact:true})).toBeChecked();
  for (const [label,value] of [['Minimum duration','80'],['Maximum duration','80'],
    ['Minimum Film personal rating','3'],['Maximum Film personal rating','3'],['Earliest year','1980'],['Latest year','1980']])
    await expect(page.getByLabel(label,{exact:true})).toHaveValue(value);
}

test.beforeAll(async ({request}) => {
  await control(request,'identity_cleanup');
  await control(request,'library_filter_fixture');
  await control(request,'library_filter_care_fixture');
});
test.afterAll(async ({request}) => { await control(request,'identity_cleanup'); });
test.beforeEach(async ({context}) => {
  await context.route('**/*', route => ['127.0.0.1','localhost'].includes(new URL(route.request().url()).hostname)
    ? route.continue() : route.abort('blockedbyclient'));
});

for (const width of [1440,390]) {
  test(`metadata pagination and Film return retain every condition and independent pages at ${width}px`, async ({page}) => {
    await page.setViewportSize({width,height:900});
    await page.goto(filmsUrl);
    await expectFilmsRestored(page);
    await page.getByRole('navigation',{name:'Library maintenance views'})
      .getByRole('link',{name:/Complete Details/}).click();
    await expect(page.locator('aside li')).toHaveCount(40);
    expect(new URL(page.url()).searchParams.get('page')).toBe('2');
    expect(new URL(page.url()).searchParams.has('metadata_page')).toBe(false);
    const reviewPages = page.getByRole('navigation',{name:'Review pages'});
    await reviewPages.getByRole('link',{name:'Next page',exact:true}).click();
    await expect(page.locator('aside li')).toHaveCount(2);
    const metadataUrl = page.url();
    for (const [key,value] of applied) expect(new URL(metadataUrl).searchParams.get(key)).toBe(value);
    expect(new URL(metadataUrl).searchParams.get('metadata_page')).toBe('2');
    await page.reload();
    await expect(page.locator('aside li')).toHaveCount(2);
    await page.screenshot({path:path.join('e2e-artifacts',`library-filter-care-${width}.png`),fullPage:true});
    await reviewPages.getByRole('link',{name:'Previous page',exact:true}).click();
    await expect(page.locator('aside li')).toHaveCount(40);
    expect(new URL(page.url()).searchParams.get('page')).toBe('2');
    await reviewPages.getByRole('link',{name:'Next page',exact:true}).click();
    await expect(page.locator('aside li')).toHaveCount(2);
    await page.getByRole('navigation',{name:'Library maintenance views'})
      .getByRole('link',{name:'All Films',exact:true}).click();
    await expectFilmsRestored(page);
    await page.goBack();
    await expect(page).toHaveURL(metadataUrl);
    await expect(page.locator('aside li')).toHaveCount(2);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}

test('each empty maintenance return restores the Film conditions and page', async ({page,request}) => {
  await control(request,'library_filter_care_fixture','empty');
  for (const view of ['metadata','inbox','offline']) {
    await page.goto(`${filmsUrl}&view=${view}&metadata_page=2`);
    await page.getByRole('link',{name:'Back to All Films',exact:true}).click();
    await expectFilmsRestored(page);
  }
});

test('completed offline cleanup returns to the unchanged filtered Film page', async ({page,request}) => {
  expect((await control(request,'library_filter_care_fixture','offline')).missing).toBe(1);
  await page.goto(`${filmsUrl}&view=offline`);
  await page.getByRole('button',{name:'Clean All 1',exact:true}).click();
  await page.getByRole('button',{name:'Clean Database Records',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Offline Records Cleaned',exact:true})).toBeVisible();
  await page.getByRole('link',{name:'Back to All Films',exact:true}).click();
  await expectFilmsRestored(page);
});
