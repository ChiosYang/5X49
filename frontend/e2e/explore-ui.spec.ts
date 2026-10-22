import { test, expect, type APIRequestContext, type Page } from '@playwright/test';
import path from 'node:path';
import en from '../messages/en.json';
import zh from '../messages/zh.json';
import type { CollectionCatalog, ExploreFilmPage } from '../src/types/movie';

const backend=process.env.E2E_BACKEND!;
const cards=(page:Page)=>page.locator('[id^="film-link-"]');
async function read(request:APIRequestContext,url:string) {
  const response=await request.get(`${backend}${url}`);expect(response.ok()).toBeTruthy();return response.json();
}
async function control(request:APIRequestContext,action:string) {
  const response=await request.post(`${backend}/__e2e/control`,{headers:{'x-e2e-token':process.env.E2E_TOKEN!},data:{action}});
  expect(response.ok()).toBeTruthy();return response.json();
}
async function capture(page:Page,name:string) {
  await page.evaluate(async()=>{
    await document.fonts.ready;
    await Promise.all([...document.images].filter(image=>{const box=image.getBoundingClientRect();return box.bottom>0&&box.top<innerHeight;}).map(image=>image.decode().catch(()=>{})));
  });
  await page.screenshot({path:path.join('e2e-artifacts',name),animations:'disabled'});
}
async function noManualUi(page:Page,copy:typeof en|typeof zh) {
  await expect(page.locator('#query-ribbon-title')).toHaveCount(0);
  await expect(page.getByRole('textbox',{name:copy.Explore.searchAll,exact:true})).toHaveCount(0);
  for(const name of ['Combined filters','组合筛选']) for(const role of ['link','button'] as const) await expect(page.getByRole(role,{name,exact:true})).toHaveCount(0);
  await expect(page.getByRole('link',{name:copy.Collections.directoryTitle,exact:true})).toHaveCount(0);
  await expect(page.getByRole('button',{name:copy.Collections.directoryTitle,exact:true})).toHaveCount(0);
  for(const text of [
    'Find a collection. Choose a film from your library.',
    '逛一个专题，挑一部库中的电影。',
    'Suggestions stay local. On submit, a complex request may send only this search text to your configured model.',
    '输入建议仅搜索本地。提交复杂需求时，可能仅将这段搜索文字发送给已配置的模型。',
  ]) await expect(page.getByText(text,{exact:true})).toHaveCount(0);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
}

test.beforeAll(async({request})=>{
  await control(request,'identity_cleanup');
  const media=path.join(process.env.E2E_ROOT!,'normal/media');
  expect((await request.put(`${backend}/settings/media-dir?media_dir=${encodeURIComponent(media)}`)).ok()).toBeTruthy();
  const scan=await request.post(`${backend}/library/scan?media_dir=${encodeURIComponent(media)}`);
  const {workflow_id}=await scan.json();
  await expect.poll(async()=>(await read(request,`/workflows/${workflow_id}`)).status,{timeout:45000}).toBe('succeeded');
  await control(request,'library_filter_fixture');
});
test.afterAll(async({request})=>{await control(request,'identity_cleanup');});
test.beforeEach(async({context})=>{
  await context.route('**/*',route=>['127.0.0.1','localhost'].includes(new URL(route.request().url()).hostname)?route.continue():route.abort('blockedbyclient'));
});

for(const [locale,copy] of [['en',en],['zh',zh]] as const) for(const width of [1440,320]) {
  test(`${locale} simplified catalog, search and correction remain usable at ${width}px`,async({page})=>{
    const errors:string[]=[],ai:string[]=[];
    page.on('pageerror',error=>errors.push(error.message));
    page.on('request',request=>{if(request.method()==='POST'&&/\/(ask|analysis)/.test(request.url()))ai.push(request.url());});
    await page.setViewportSize({width,height:900});await page.goto(`/${locale}/explore`);
    const input=page.getByRole('searchbox',{name:copy.Discovery.label,exact:true});
    await expect(input).toBeVisible();await expect(page.locator('#collection-directory-title')).toHaveText(copy.Collections.directoryTitle);
    await expect(cards(page)).toHaveCount(0);await noManualUi(page,copy);await capture(page,`simplified-home-${locale}-${width}.png`);
    await input.fill(locale==='zh'?'未看过的日本电影':'unwatched Japanese films');await input.press('Enter');
    await expect.poll(()=>new URL(page.url()).searchParams.has('p')).toBe(true);
    await expect(cards(page)).not.toHaveCount(0);await noManualUi(page,copy);
    const conditions=page.getByRole('region',{name:copy.Discovery.conditions,exact:true});
    await expect(conditions).toBeVisible();await expect(conditions.getByRole('button')).not.toHaveCount(0);
    await capture(page,`simplified-conditions-${locale}-${width}.png`);
    const inputValue=await input.inputValue();await conditions.getByRole('button').first().click();
    await expect(input).toHaveValue(inputValue);await noManualUi(page,copy);
    await input.fill('Japanese films featuring ~/Movies/private.mkv');await input.press('Enter');
    const error=page.locator('form[role="search"] [role="alert"]');await expect(error).toBeVisible();
    await expect(input).toHaveAttribute('aria-describedby',await error.getAttribute('id')||'');
    await noManualUi(page,copy);await capture(page,`simplified-error-${locale}-${width}.png`);
    expect(errors).toEqual([]);expect(ai).toEqual([]);
  });
}

for(const locale of ['en','zh']) test(`${locale} retired filter URLs redirect without restoring the form or executing old facets`,async({page})=>{
  const copy=locale==='en'?en:zh;
  for(const suffix of ['/explore/filter?country=JP&view=unwatched&offset=40','/explore?person=unknown&person_match=any&decade=1980']) {
    await page.goto(`/${locale}${suffix}`);await expect(page).toHaveURL(/\/(?:en\/|zh\/)?explore$/);
    await expect(page.locator('#collection-directory-title')).toHaveText(copy.Collections.directoryTitle);await noManualUi(page,copy);
  }
  await page.goto(`/${locale}/explore/filter?q=Orbit&country=JP`);
  await expect.poll(()=>new URL(page.url()).pathname.endsWith('/explore/search')).toBe(true);
  expect(new URL(page.url()).searchParams.get('q')).toBe('Orbit');expect(new URL(page.url()).searchParams.has('p')).toBe(false);
  expect(new URL(page.url()).searchParams.has('country')).toBe(false);await expect(cards(page)).toHaveCount(5);await noManualUi(page,copy);
});

test('legacy directory alias preserves category and offset on the canonical home',async({page})=>{
  await page.goto('/en/explore/collections?category=country&offset=1');
  await expect(page).toHaveURL(/\/en\/explore\?category=country&offset=1$/);
  await expect(page.getByRole('link',{name:new RegExp('^'+en.Collections.categories.country+' \\(')})).toHaveAttribute('aria-current','page');
  await page.reload();await expect(page).toHaveURL(/\/en\/explore\?category=country&offset=1$/);
  await noManualUi(page,en);
});

test('search clear returns to its catalog category, scroll and history entry',async({page})=>{
  await page.setViewportSize({width:390,height:844});await page.goto('/en/explore?category=country');
  const link=page.locator('a[href*="/explore/collections/country/"]').last();
  await link.scrollIntoViewIfNeeded();const y=await page.evaluate(()=>scrollY),home=page.url();
  const input=page.getByRole('searchbox',{name:en.Discovery.label,exact:true});
  await input.fill('Orbit');
  await input.evaluate((node,y)=>{node.focus({preventScroll:true});window.scrollTo(0,y);},y);
  await page.keyboard.press('Enter');await expect(cards(page)).toHaveCount(5);
  const search=page.url(),history=await page.evaluate(()=>window.history.length);
  await page.getByRole('button',{name:en.Discovery.clear,exact:true}).click();
  await expect(page).toHaveURL(home);await expect(input).toHaveValue('');
  await expect.poll(()=>page.evaluate(before=>Math.abs(scrollY-Math.max(0,Math.min(before,document.documentElement.scrollHeight-innerHeight))),y)).toBeLessThanOrEqual(2);
  expect(await page.evaluate(()=>window.history.length)).toBe(history+1);
  await page.goBack();await expect(page).toHaveURL(search);await expect(input).toHaveValue('Orbit');await expect(cards(page)).toHaveCount(5);
  await page.goBack();await expect(page).toHaveURL(home);
  await page.goForward();await expect(page).toHaveURL(search);
  await input.fill('');await input.press('Enter');await expect(page).toHaveURL(home);
  await page.goBack();await expect(page).toHaveURL(search);await expect(input).toHaveValue('Orbit');
});

test('a late invalid collection page cannot replace newer viewing navigation',async({page,request})=>{
  const all:ExploreFilmPage=await read(request,'/explore/films?decade=1980&sort=year&dir=asc&limit=100');expect(all.total).toBe(42);
  for(const {film} of all.items)expect((await request.put(`${backend}/films/${film.id}/profile-state`,{data:{watched:false}})).ok()).toBeTruthy();
  expect((await request.put(`${backend}/films/${all.items[0].film.id}/profile-state`,{data:{watched:true}})).ok()).toBeTruthy();
  const first='/en/explore/collections/decade/1980?view=unwatched&sort=year&dir=asc';
  await page.goto(first);await page.getByRole('button',{name:'Next',exact:true}).click();await expect(cards(page)).toHaveCount(1);
  let release!:()=>void,captured!:()=>void;
  const held=new Promise<void>(resolve=>{release=resolve;}),fetched=new Promise<void>(resolve=>{captured=resolve;});
  await page.route('**/en/explore/collections/decade/1980?**',async route=>{
    if(route.request().headers().rsc==='1'&&new URL(route.request().url()).searchParams.get('offset')==='40'){
      const response=await route.fetch();captured();await held;await route.fulfill({response}).catch(()=>{});
    }else await route.continue();
  });
  try{
    const trigger=cards(page).first();await trigger.click();
    await page.locator('.library-card-media').filter({has:trigger}).getByRole('button',{name:en.Library.markWatched,exact:true}).click();await fetched;
    const history=await page.evaluate(()=>window.history.length);
    const allButton=page.getByRole('group',{name:en.Explore.viewLabel,exact:true}).getByRole('button',{name:'All',exact:true});
    await allButton.click();await allButton.focus();release();
    await expect(page).toHaveURL(new URL('/en/explore/collections/decade/1980?sort=year&dir=asc',page.url()).href);
    await expect(page.locator('#explore-results-title')).toHaveText('42 Films');await expect(cards(page)).toHaveCount(40);
    await expect(allButton).toBeFocused();expect(await page.evaluate(()=>window.history.length)).toBe(history+1);
  }finally{release();}
});

test('a save completing in film detail leaves navigation alone and updates cached Collection Back',async({page,request})=>{
  const films:ExploreFilmPage=await read(request,'/explore/films?country=JP');
  for(const {film} of films.items)expect((await request.put(`${backend}/films/${film.id}/profile-state`,{data:{watched:false}})).ok()).toBeTruthy();
  await page.goto('/en/explore/collections/country/JP?view=unwatched');await expect(cards(page)).toHaveCount(2);
  const target=films.items[0].film,href=page.url();let release!:()=>void;
  const gate=new Promise<void>(resolve=>{release=resolve;});let writes=0,track=false;const refreshes:string[]=[];
  await page.route(`**/api/films/${target.id}/profile-state`,async route=>{if(route.request().method()==='PUT'){writes++;await gate;}await route.continue();});
  page.on('request',request=>{if(track&&request.headers().rsc==='1'&&request.headers()['next-router-prefetch']!=='1')refreshes.push(request.url());});
  try{
    const trigger=page.locator(`#film-link-${target.id}`);await trigger.click();
    await page.locator('.library-card-media').filter({has:trigger}).getByRole('button',{name:en.Library.markWatched,exact:true}).click();await expect.poll(()=>writes).toBe(1);
    await page.keyboard.press('Escape');await page.locator(`.library-card-title[href="/en/library/${target.id}"]`).click();await expect(page).toHaveURL(new RegExp(`/library/${target.id}$`));
    const back=page.getByRole('button',{name:en.FilmDetail.return,exact:true});await back.focus();const detail=page.url(),history=await page.evaluate(()=>window.history.length);
    track=true;release();await expect.poll(async()=>(await read(request,`/films/${target.id}/profile-state`)).watched).toBe(true);
    await expect(page).toHaveURL(detail);await expect(back).toBeFocused();expect(await page.evaluate(()=>window.history.length)).toBe(history);expect(refreshes).toEqual([]);
    track=false;await page.goBack();await expect(page).toHaveURL(href);await expect(cards(page)).toHaveCount(1);expect(writes).toBe(1);
  }finally{release();}
});

test('the default catalog paginates every local topic, and clear restores that page',async({page,request})=>{
  await control(request,'catalog_pagination_fixture');
  try{
    const catalog:CollectionCatalog=await read(request,'/explore/catalog?limit=24');expect(catalog.total).toBeGreaterThan(24);
    await page.goto('/en/explore');const seen=new Set<string>();
    const entries=()=>page.locator('a[href*="/explore/collections/"]');
    const remember=async()=>{for(const href of await entries().evaluateAll(links=>links.map(link=>link.getAttribute('href')!))){expect(seen.has(href)).toBe(false);seen.add(href);}};
    await expect(entries()).toHaveCount(24);await remember();
    while(await page.getByRole('link',{name:en.Collections.next,exact:true}).count()){
      const next=page.getByRole('link',{name:en.Collections.next,exact:true}),target=await next.getAttribute('href');
      await next.click();await expect(page).toHaveURL(new URL(target!,page.url()).href);await remember();
    }
    expect(seen.size).toBe(catalog.total);
    const last=page.url(),count=await entries().count();await page.reload();await expect(page).toHaveURL(last);await expect(entries()).toHaveCount(count);
    const input=page.getByRole('searchbox',{name:en.Discovery.label,exact:true});await input.fill('Orbit');await input.press('Enter');await expect(cards(page)).toHaveCount(5);
    await page.getByRole('button',{name:en.Discovery.clear,exact:true}).click();await expect(page).toHaveURL(last);await expect(entries()).toHaveCount(count);
    await noManualUi(page,en);
  }finally{await control(request,'catalog_pagination_cleanup');}
});
