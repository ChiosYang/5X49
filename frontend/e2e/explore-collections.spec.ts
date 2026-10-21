import { test, expect, type APIRequestContext, type Page } from '@playwright/test';
import path from 'node:path';
import en from '../messages/en.json';
import zh from '../messages/zh.json';
import type { CollectionCatalog, LocalCollection, LocalCollectionPage, ExploreFilmPage } from '../src/types/movie';

const backend = process.env.E2E_BACKEND!;
const cards = (page: Page) => page.locator('[id^="film-link-"]');
async function read(request: APIRequestContext, url: string) {
  const response = await request.get(`${backend}${url}`); expect(response.ok()).toBeTruthy(); return response.json();
}
async function control(request: APIRequestContext, action: string) {
  const response = await request.post(`${backend}/__e2e/control`, { headers: { 'x-e2e-token': process.env.E2E_TOKEN! }, data: { action } });
  expect(response.ok()).toBeTruthy(); return response.json();
}
function collectionTitle(item: LocalCollection, locale: string) {
  const copy = locale === 'zh' ? zh.Collections : en.Collections;
  const label = item.kind === 'country' ? new Intl.DisplayNames([locale], {type:'region'}).of(item.key)!
    : item.kind === 'decade' ? locale === 'zh' ? `${item.key}年代` : `${item.key}s` : item.label;
  return copy.titles[item.kind].replace('{label}', label);
}
async function noOverflow(page: Page) { expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true); }
async function capture(page: Page, name: string) {
  await page.evaluate(async () => { await document.fonts.ready; await Promise.all([...document.images].map(image => image.decode().catch(() => {}))); });
  await page.screenshot({ path: path.join('e2e-artifacts', name), animations:'disabled' });
}
test.beforeAll(async ({request}) => {
  await control(request, 'identity_cleanup');
  const media = path.join(process.env.E2E_ROOT!, 'normal/media');
  expect((await request.put(`${backend}/settings/media-dir?media_dir=${encodeURIComponent(media)}`)).ok()).toBeTruthy();
  const scan = await request.post(`${backend}/library/scan?media_dir=${encodeURIComponent(media)}`);
  const { workflow_id } = await scan.json();
  await expect.poll(async () => (await read(request, `/workflows/${workflow_id}`)).status, {timeout:45000}).toBe('succeeded');
  await control(request, 'library_filter_fixture');
});
test.afterAll(async ({request}) => { await control(request, 'identity_cleanup'); });
test.beforeEach(async ({context}) => {
  await context.route('**/*', route => ['127.0.0.1','localhost'].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort('blockedbyclient'));
});

for (const locale of ['en','zh']) for (const width of [1920,1024,768,390,320]) {
  test(`${locale} collection shelves, directory and detail preserve the hierarchy at ${width}px`, async ({page,request}) => {
    const copy = locale === 'zh' ? zh.Collections : en.Collections;
    const explore = locale === 'zh' ? zh.Explore : en.Explore;
    const errors: string[] = [], ai: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => { if (request.method() === 'POST' && /\/(ask|analysis)/.test(request.url())) ai.push(request.url()); });
    await page.setViewportSize({width,height:width === 1920 ? 1080 : 844});
    await page.goto(`/${locale}/explore`);
    const catalog: CollectionCatalog = await read(request,'/explore/catalog?featured=true&limit=3');
    expect(catalog.items.length).toBeGreaterThan(0);
    await expect(page.locator('h1')).toHaveText(copy.homeTitle);
    await expect(page.locator('#explore-results-title')).toHaveCount(0);
    await expect(page.getByRole('textbox',{name:explore.searchAll,exact:true})).toHaveCount(0);
    await expect(cards(page)).toHaveCount(catalog.items.reduce((sum,item) => sum+item.previews.length,0));
    expect(await cards(page).evaluateAll(nodes => new Set(nodes.map(node => node.id)).size)).toBe(await cards(page).count());
    await noOverflow(page);
    if ([1920,390].includes(width)) await capture(page,`collection-home-${locale}-${width}.png`);
    const item = catalog.items.at(-1)!;
    const title = collectionTitle(item,locale);
    const shelf = page.getByRole('region',{name:title,exact:true});
    const link = shelf.getByRole('link',{name:copy.viewCollection.replace('{title}',title),exact:true});
    await link.scrollIntoViewIfNeeded(); await link.focus();
    const before = await page.evaluate(() => scrollY);
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(new RegExp(`/explore/collections/${item.kind}/${item.key}$`));
    await expect(page.locator('h1')).toHaveText(title);
    await expect(page.locator('#explore-results-title')).toHaveText(new RegExp(`^${item.count}\\b`));
    await expect(cards(page)).toHaveCount(Math.min(40,item.count));
    await expect(page.getByRole('region',{name:explore.activeFilters,exact:true})).toHaveCount(0);
    await expect(page.getByRole('textbox',{name:explore.searchAll,exact:true})).toHaveCount(0);
    await noOverflow(page);
    if ([1920,390].includes(width)) await capture(page,`collection-detail-${locale}-${width}.png`);
    await page.getByRole('navigation',{name:copy.breadcrumb,exact:true}).getByRole('link',{name:copy.homeTitle,exact:true}).click();
    await expect(page).toHaveURL(locale === 'zh' ? /\/(?:zh\/)?explore$/ : /\/en\/explore$/);
    await expect.poll(() => page.evaluate(y => Math.abs(scrollY-Math.min(y,document.documentElement.scrollHeight-innerHeight)),before)).toBeLessThanOrEqual(2);
    await page.getByRole('link',{name:copy.directoryTitle,exact:true}).first().click();
    await expect(page.locator('h1')).toHaveText(copy.directoryTitle);
    await page.getByRole('navigation',{name:copy.categoryLabel,exact:true}).getByRole('link',{name:new RegExp(`^${copy.categories.country}`)}).click();
    await expect.poll(() => new URL(page.url()).searchParams.get('category')).toBe('country');
    await expect(cards(page)).toHaveCount(0);
    await expect(page.locator('a[href*="/explore/collections/country/"]')).not.toHaveCount(0);
    await page.reload(); await noOverflow(page);
    if ([1920,390].includes(width)) await capture(page,`collection-directory-${locale}-${width}.png`);
    expect(errors).toEqual([]); expect(ai).toEqual([]);
  });
}

test('collection view, sorting, pagination and browser history retain stable identity', async ({page,request}) => {
  const href = '/en/explore/collections/decade/1980';
  const initial: LocalCollectionPage = await read(request,'/explore/collections/decade/1980');
  await page.goto(href); await expect(cards(page)).toHaveCount(40);
  const views = page.getByRole('group',{name:en.Explore.viewLabel,exact:true});
  await views.getByRole('button',{name:'Unwatched',exact:true}).click();
  await expect.poll(()=>new URL(page.url()).searchParams.get('view')).toBe('unwatched');
  const unwatched = page.url();
  await page.getByRole('button',{name:'Year',exact:true}).click();
  await expect.poll(()=>new URL(page.url()).searchParams.get('sort')).toBe('year');
  const sorted = page.url(); await page.reload(); await expect(page).toHaveURL(sorted);
  await expect(views.getByRole('button',{name:'Unwatched',exact:true})).toHaveAttribute('aria-pressed','true');
  await expect(page.getByRole('button',{name:'Year',exact:true})).toHaveAttribute('aria-pressed','true');
  await expect(page.locator('h1')).toHaveText('The 1980s');
  await expect(page.getByText(`${initial.collection.count} local films released in the 1980s.`,{exact:true})).toBeVisible();
  await page.goBack(); await expect(page).toHaveURL(unwatched);
  await page.goForward(); await expect(page).toHaveURL(sorted);
  await views.getByRole('button',{name:'All',exact:true}).click();
  await expect.poll(()=>new URL(page.url()).searchParams.has('view')).toBe(false);
  await page.getByRole('button',{name:'Next',exact:true}).click();
  await expect.poll(() => new URL(page.url()).searchParams.get('offset')).toBe('40');
  await expect(page.locator('#explore-results-title')).toBeFocused();
  const pageUrl=page.url(); await page.reload(); await expect(page).toHaveURL(pageUrl);
  await expect(cards(page)).toHaveCount(initial.results.total-40);
});

for (const locale of ['en','zh']) test(`${locale} discovery search reuses Library film matches and opens person collections`, async ({page,request}) => {
  const copy = locale === 'zh' ? zh.Collections : en.Collections;
  const searchCopy = locale === 'zh' ? zh.LibrarySearch : en.LibrarySearch;
  await page.goto(`/${locale}/explore`);
  await page.getByRole('link',{name:copy.searchTitle,exact:true}).click();
  const input=page.getByRole('searchbox',{name:searchCopy.query,exact:true});
  await input.fill('Director 1'); await input.press('Enter');
  await expect.poll(() => new URL(page.url()).searchParams.get('q')).toBe('Director 1');
  const expected=await read(request,'/library/films/page?q=Director+1&limit=40');
  await expect(cards(page)).toHaveCount(expected.items.length);
  const people=page.locator('[aria-labelledby="search-people-title"]');
  const person=people.getByRole('link').filter({has:page.getByText('Director 1',{exact:true})});
  await expect(person).toBeVisible(); const href=await person.getAttribute('href');
  expect(href).toContain('/explore/collections/person/');
  await person.click(); await expect(page).toHaveURL(new RegExp('/collections/person/person_[a-f0-9]{32}$'));
  await expect(page.locator('h1')).toHaveText(copy.titles.person.replace('{label}','Director 1'));
  await page.goBack(); await expect(input).toHaveValue('Director 1');
  await input.fill(locale==='zh'?'日本':'Japan'); await input.press('Enter');
  await page.locator('a[href$="/explore/collections/country/JP"]').click();
  await expect(page).toHaveURL(new RegExp('/collections/country/JP$'));
  await expect(page.locator('#query-ribbon-title')).toHaveCount(0);
});

for (const width of [1440,390]) test(`home shelves refresh watched/favorite counters once and keep position at ${width}px`,async ({page,request}) => {
  const first: CollectionCatalog = await read(request,'/explore/catalog?featured=true&limit=3');
  const item=first.items[0], film=item.previews[0];
  expect((await request.put(`${backend}/films/${film.id}/profile-state`,{data:{watched:false,favorite:false}})).ok()).toBeTruthy();
  await page.setViewportSize({width,height:1000}); await page.goto('/en/explore');
  const catalog: CollectionCatalog = await read(request,'/explore/catalog?featured=true&limit=3');
  const current=catalog.items.find(entry=>entry.id===item.id)!;
  const title=collectionTitle(current,'en'); const shelf=page.getByRole('region',{name:title,exact:true});
  await expect(shelf.getByText(`${current.unwatched_count} unwatched`,{exact:false})).toBeVisible();
  const history=await page.evaluate(()=>window.history.length); let refreshes=0,writes=0;
  page.on('request',request=>{const u=new URL(request.url()); if(u.pathname==='/en/explore'&&request.headers().rsc==='1')refreshes++; if(request.method()==='PUT'&&u.pathname===`/api/films/${film.id}/profile-state`)writes++;});
  const trigger=page.locator(`#film-link-${film.id}`); await trigger.click();
  const panel=shelf.locator('.library-card-media').filter({has:trigger}).locator('.library-card-inspector');
  await panel.getByRole('button',{name:en.Library.favorite,exact:true}).click();
  await expect.poll(()=>refreshes).toBe(1); await expect(panel.getByRole('button',{name:en.Library.unfavorite,exact:true})).toBeVisible();
  const watched=panel.getByRole('button',{name:en.Library.markWatched,exact:true}); await watched.scrollIntoViewIfNeeded();
  const y=await page.evaluate(()=>scrollY); await watched.click();
  await expect(shelf.getByText(`${current.unwatched_count-1} unwatched`,{exact:false})).toBeVisible();
  expect(refreshes).toBe(2); expect(writes).toBe(2); expect(await page.evaluate(()=>window.history.length)).toBe(history);
  await expect.poll(()=>page.evaluate(before=>Math.abs(scrollY-Math.max(0,Math.min(before,document.documentElement.scrollHeight-innerHeight))),y)).toBeLessThanOrEqual(1);
});

test('collection last page shrinks 41 to 40 using replace with identity, view and sort intact',async ({page,request})=>{
  const all: ExploreFilmPage=await read(request,'/explore/films?decade=1980&limit=100');
  for(const {film} of all.items) expect((await request.put(`${backend}/films/${film.id}/profile-state`,{data:{watched:false}})).ok()).toBeTruthy();
  expect((await request.put(`${backend}/films/${all.items[0].film.id}/profile-state`,{data:{watched:true}})).ok()).toBeTruthy();
  const href='/en/explore/collections/decade/1980?view=unwatched&sort=year&dir=asc';
  await page.goto(href); await page.getByRole('button',{name:'Next',exact:true}).click();
  await expect(cards(page)).toHaveCount(1); const history=await page.evaluate(()=>window.history.length);
  const trigger=cards(page).first(); await trigger.click();
  await page.locator('.library-card-media').filter({has:trigger}).getByRole('button',{name:en.Library.markWatched,exact:true}).click();
  await expect(page).toHaveURL(new URL(href,page.url()).href);
  await expect(cards(page)).toHaveCount(40); await expect(page.locator('#explore-results-title')).toHaveText('40 Films');
  expect(await page.evaluate(()=>window.history.length)).toBe(history);
});

test('saving inside a collection updates the cached directory and home on Back',async ({page,request})=>{
  await page.goto('/en/explore'); await page.getByRole('link',{name:en.Collections.directoryTitle,exact:true}).first().click();
  await expect(page).toHaveURL(/\/en\/explore\/collections$/);
  await expect(page.getByRole('heading',{name:en.Collections.directoryTitle,exact:true})).toBeVisible();
  const href='/en/explore/collections/country/JP';
  const directory: CollectionCatalog=await read(request,'/explore/catalog');
  expect(directory.items.some(item=>item.kind==='country'&&item.key==='JP')).toBe(true);
  const before: LocalCollectionPage=await read(request,'/explore/collections/country/JP');
  const target=before.collection.previews[0];
  expect((await request.put(`${backend}/films/${target.id}/profile-state`,{data:{watched:false}})).ok()).toBeTruthy();
  await page.reload();
  await expect(page.getByRole('heading',{name:en.Collections.directoryTitle,exact:true})).toBeVisible();
  const directoryHref=page.url();
  await page.locator(`a[href="${href}"]`).click();
  const trigger=page.locator(`#film-link-${target.id}`); await trigger.click();
  await page.locator('.library-card-media').filter({has:trigger}).getByRole('button',{name:en.Library.markWatched,exact:true}).click();
  await expect(trigger.getByLabel(en.Library.watched,{exact:true})).toHaveCount(1);
  const after: LocalCollectionPage=await read(request,'/explore/collections/country/JP');
  await page.goBack(); await expect(page).toHaveURL(directoryHref);
  const entry=page.locator(`a[href="${href}"]`);
  await expect(entry.getByText(`${after.collection.unwatched_count} unwatched`,{exact:false})).toBeVisible();
  await page.goBack(); await expect(page).toHaveURL(new RegExp('/en/explore$'));
  const home: CollectionCatalog=await read(request,'/explore/catalog?featured=true&limit=3');
  for(const item of home.items) await expect(page.getByRole('region',{name:collectionTitle(item,'en'),exact:true}).getByText(`${item.unwatched_count} unwatched`,{exact:false})).toBeVisible();
});

test('a delayed home save cannot cancel a pending collection Link and cached Back stays fresh',async ({page,request})=>{
  const catalog: CollectionCatalog=await read(request,'/explore/catalog?featured=true&limit=3');
  const item=catalog.items[0], target=item.previews[0];
  expect((await request.put(`${backend}/films/${target.id}/profile-state`,{data:{watched:false}})).ok()).toBeTruthy();
  await page.goto('/en/explore');
  let releaseSave!:()=>void,releaseRead!:()=>void,captured!:()=>void;
  const saveHeld=new Promise<void>(resolve=>{releaseSave=resolve;});
  const readHeld=new Promise<void>(resolve=>{releaseRead=resolve;});
  const readCaptured=new Promise<void>(resolve=>{captured=resolve;});
  const path=`/en/explore/collections/${item.kind}/${item.key}`;
  let writes=0,homeRefreshes=0,hold=true,track=false;
  await page.route(`**/api/films/${target.id}/profile-state`,async route=>{if(route.request().method()==='PUT'){writes++;await saveHeld;}await route.continue();});
  await page.route(`**${path}*`,async route=>{
    if(hold&&route.request().headers().rsc==='1'&&route.request().headers()['next-router-prefetch']!=='1'){hold=false;const response=await route.fetch();captured();await readHeld;await route.fulfill({response}).catch(()=>{});}else await route.continue();
  });
  page.on('request',request=>{if(track&&new URL(request.url()).pathname==='/en/explore'&&request.headers().rsc==='1'&&request.headers()['next-router-prefetch']!=='1')homeRefreshes++;});
  try {
    const shelf=page.getByRole('region',{name:collectionTitle(item,'en'),exact:true});
    const trigger=page.locator(`#film-link-${target.id}`);await trigger.click();
    await shelf.locator('.library-card-media').filter({has:trigger}).getByRole('button',{name:en.Library.markWatched,exact:true}).click();
    await expect.poll(()=>writes).toBe(1);await page.keyboard.press('Escape');
    await shelf.getByRole('link',{name:en.Collections.viewCollection.replace('{title}',collectionTitle(item,'en')),exact:true}).click();
    await readCaptured;track=true;releaseSave();
    await expect.poll(async()=>(await read(request,`/films/${target.id}/profile-state`)).watched).toBe(true);
    expect(homeRefreshes).toBe(0);releaseRead();
    await expect(page).toHaveURL(new RegExp(`${path}$`));
    await expect(page.locator(`#film-link-${target.id}`).getByLabel(en.Library.watched,{exact:true})).toHaveCount(1);
    await page.goBack();await expect(page).toHaveURL(/\/en\/explore$/);
    const current: CollectionCatalog=await read(request,'/explore/catalog?featured=true&limit=3');
    const latest=current.items.find(entry=>entry.id===item.id)!;
    await expect(shelf.getByText(`${latest.unwatched_count} unwatched`,{exact:false})).toBeVisible();
    expect(writes).toBe(1);
  }finally{releaseSave();releaseRead();}
});

for (const locale of ['en','zh']) for (const width of [1440,390]) for (const mode of ['collection','filter','search']) {
  test(`${locale} ${mode} page Return restores query, history, focus and scroll at ${width}px`, async ({page,request})=>{
    const copy=locale==='en'?en:zh, prefix=`/${locale}`;
    const all: ExploreFilmPage=await read(request,'/explore/films?decade=1980&limit=100');
    for(const {film} of all.items) if(film.profile_state.watched) expect((await request.put(`${backend}/films/${film.id}/profile-state`,{data:{watched:false}})).ok()).toBeTruthy();
    const list=mode==='collection'?'/explore/collections/decade/1980?view=unwatched&sort=year&dir=asc&offset=40'
      :mode==='filter'?'/explore/filter?decade=1980&view=unwatched&sort=year&dir=asc&offset=40'
        :'/explore/search?q=Shelf&page=2';
    await page.setViewportSize({width,height:900});
    await page.goto(`${prefix}/explore`);const previous=page.url();
    await page.goto(prefix+list);await expect(cards(page)).toHaveCount(2);
    await expect(page.locator('html')).toHaveAttribute('lang',locale);
    const href=page.url(), history=await page.evaluate(()=>window.history.length);
    const link=page.locator('.library-card-title').first();
    const filmHref=(await link.getAttribute('href'))!, filmId=filmHref.split('/').at(-1)!;
    await link.scrollIntoViewIfNeeded();await link.focus();
    await link.evaluate(node=>node.scrollIntoView({block:'center',behavior:'instant'}));
    const y=await page.evaluate(()=>scrollY);
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(new RegExp(`/library/${filmId}$`));
    const remembered=await page.evaluate(()=>JSON.parse(sessionStorage.getItem('5x49:return-context:v1')||'null'));
    const source=new URL(href);
    expect(remembered).toMatchObject({href:source.pathname+source.search,filmId,scrollY:y});
    expect(await page.evaluate(()=>window.history.length)).toBe(history+1);
    const button=page.getByRole('button',{name:copy.FilmDetail.return,exact:true});
    await expect(button).toBeEnabled();
    await button.focus();await page.keyboard.press('Enter');
    await expect(page).toHaveURL(href);await expect(cards(page)).toHaveCount(2);
    await expect(page.locator(`#film-link-${filmId}`)).toBeFocused();
    await expect.poll(()=>page.evaluate(before=>Math.abs(scrollY-Math.max(0,Math.min(before,document.documentElement.scrollHeight-innerHeight))),y)).toBeLessThanOrEqual(1);
    expect(await page.evaluate(()=>window.history.length)).toBe(history+2);
    await page.goBack();await expect(page).toHaveURL(new RegExp(`/library/${filmId}$`));
    await page.goBack();await expect(page).toHaveURL(href);await expect(cards(page)).toHaveCount(2);
    await page.goBack();await expect(page).toHaveURL(previous);
  });
}

test('empty and sparse libraries offer honest collection fallbacks and working film search',async ({page,request})=>{
  await control(request,'identity_cleanup'); await page.goto('/en/explore');
  await expect(page.getByText(en.Collections.emptyDescription,{exact:true})).toBeVisible();
  await expect(cards(page)).toHaveCount(0); await page.goto('/en/explore/collections');
  await expect(page.getByRole('link',{name:en.Collections.openLibrary,exact:true})).toBeVisible();
  await control(request,'explore_sparse_fixture'); await page.goto('/en/explore');
  await expect(page.getByText(en.Collections.sparseDescription,{exact:true})).toBeVisible(); await expect(cards(page)).toHaveCount(0);
  await page.getByRole('link',{name:en.Collections.searchTitle,exact:true}).click();
  await page.getByRole('searchbox',{name:en.LibrarySearch.query,exact:true}).fill('Explore Unknown');
  await page.getByRole('searchbox',{name:en.LibrarySearch.query,exact:true}).press('Enter');
  await expect(cards(page)).toHaveCount(1); await expect(page.getByText(en.Collections.noCollections,{exact:true})).toBeVisible();
  await expect(page.getByText(en.Collections.noPeople,{exact:true})).toBeVisible();
});
