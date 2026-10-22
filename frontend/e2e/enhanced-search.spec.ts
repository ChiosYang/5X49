import { test, expect, type APIRequestContext, type Page } from '@playwright/test';
import path from 'node:path';
import en from '../messages/en.json';
import zh from '../messages/zh.json';

const backend=process.env.E2E_BACKEND!;
const cards=(page:Page)=>page.locator('[id^="film-link-"]');
const input=(page:Page,locale='en')=>page.getByRole('searchbox',{name:(locale==='zh'?zh:en).Discovery.label,exact:true});
let ids:Record<string,string>;
async function control(request:APIRequestContext,action:string,extra:object={}){
  const response=await request.post(`${backend}/__e2e/control`,{headers:{'x-e2e-token':process.env.E2E_TOKEN!},data:{action,...extra}});
  expect(response.ok()).toBeTruthy();return response.json();
}
async function read(request:APIRequestContext,url:string){const response=await request.get(backend+url);expect(response.ok()).toBeTruthy();return response.json();}
async function submit(page:Page,question:string,locale='en'){
  await expect(input(page,locale)).toBeEnabled();await input(page,locale).fill(question);
  const replied=page.waitForResponse(r=>r.url().endsWith('/api/explore/search/interpret')&&r.request().method()==='POST');
  await input(page,locale).press('Enter');const resolution=await(await replied).json();
  await expect.poll(()=>new URL(page.url()).searchParams.get('q')).toBe(question);
  await expect.poll(()=>new URL(page.url()).searchParams.get('p')).toBe(resolution.plan?JSON.stringify(resolution.plan):null);
  return resolution;
}
async function capture(page:Page,name:string){
  await page.evaluate(async()=>{await document.fonts.ready;await Promise.all([...document.images].filter(i=>i.getBoundingClientRect().top<innerHeight).map(i=>i.decode().catch(()=>{})));});
  await page.screenshot({path:path.join('e2e-artifacts',name),animations:'disabled'});
}
test.beforeAll(async({request})=>{
  await control(request,'identity_cleanup');
  ids=await control(request,'enhanced_search_fixture');
});
test.beforeEach(async({context,request})=>{
  await control(request,'discovery_ai',{enabled:true});
  await context.route('**/*',route=>['127.0.0.1','localhost'].includes(new URL(route.request().url()).hostname)?route.continue():route.abort('blockedbyclient'));
});
test.afterEach(async({request})=>{await control(request,'discovery_ai',{enabled:false});});
test.afterAll(async({request})=>{await control(request,'identity_cleanup');});

for(const locale of ['en','zh'])for(const width of [1440,320]){
  test(`${locale} complete extended conditions, removable bounds and Return at ${width}px`,async({page,request})=>{
    const copy=locale==='zh'?zh:en;await page.setViewportSize({width,height:900});await page.goto(`/${locale}/explore`);
    const question=locale==='zh'?'未看日本或法国动作或剧情电影，2098年，由本地导演甲执导，少于90分钟'
      :'unwatched Japanese or French action or drama films in 2098 directed by Search Director under 90 minutes';
    const result=await submit(page,question,locale);expect(result.version).toBe('discovery.v2');
    await expect(cards(page)).toHaveCount(1);await expect(page.locator('#film-link-'+ids['Search Alpha'])).toBeVisible();
    await expect(page.getByText(copy.Discovery.extendedConditions,{exact:true})).toBeVisible();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await capture(page,`enhanced-conditions-${locale}-${width}.png`);
    const href=page.url();
    await page.locator('.library-card-title').first().click();
    await expect(page.getByRole('button',{name:copy.FilmDetail.return,exact:true})).toBeVisible();
    await page.getByRole('button',{name:copy.FilmDetail.return,exact:true}).click();
    await expect(page).toHaveURL(href);await expect(cards(page)).toHaveCount(1);
    const label=copy.Discovery.durationCondition.replace('{value}','< 90');
    await page.getByRole('button',{name:copy.Discovery.remove.replace('{condition}',label),exact:true}).click();
    await expect(cards(page)).toHaveCount(2);await expect.poll(()=>new URL(page.url()).searchParams.get('edited')).toBe('1');
    await page.reload();await expect(cards(page)).toHaveCount(2);await expect(input(page,locale)).toHaveValue(question);
    await page.goBack();await expect(page).toHaveURL(href);await expect(cards(page)).toHaveCount(1);
    expect((await control(request,'discovery_ai_stats')).calls).toBe(0);
  });
  test(`${locale} literal aliases and exact title priority at ${width}px`,async({page,request})=>{
    await page.setViewportSize({width,height:844});await page.goto(`/${locale}/explore`);
    for(const question of ['星际回声','Echo Films 2098']){
      await submit(page,question,locale);await expect(cards(page)).toHaveCount(1);
      await expect(page.locator('#film-link-'+ids['Search Beta'])).toBeVisible();
      await expect(page.locator('#discovery-conditions-title')).toHaveCount(0);
    }
    await submit(page,'本地导演甲',locale);await expect(cards(page)).toHaveCount(3);
    expect(await page.locator('#search-films-title').evaluate(el=>Boolean(el.compareDocumentPosition(
      document.getElementById('search-collections-title')!) & Node.DOCUMENT_POSITION_FOLLOWING))).toBe(true);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await capture(page,`enhanced-alias-${locale}-${width}.png`);
    expect((await control(request,'discovery_ai_stats')).calls).toBe(0);
  });
}
for(const locale of ['en','zh'])test(locale+' multiple-person identity clarification survives reload and Back',async({page,request})=>{
  const copy=locale==='zh'?zh:en;await page.goto(`/${locale}/explore`);
  await submit(page,'films starring Search Actor in 2098',locale);
  await expect(page.getByRole('heading',{name:copy.Discovery.states.needs_clarification,exact:true})).toBeVisible();
  const choices=page.getByRole('button',{name:/^Search Actor/});await expect(choices).toHaveCount(2);
  await choices.filter({hasText:'Search Alpha'}).click();await expect(cards(page)).toHaveCount(1);
  const href=page.url();expect(new URL(href).searchParams.get('people_ids')).not.toBeNull();
  await page.reload();await expect(cards(page)).toHaveCount(1);
  const chip=page.locator('[aria-labelledby="discovery-conditions-title"] button').filter({hasText:'Search Actor'});
  await chip.click();await expect(cards(page)).toHaveCount(2);
  await page.goBack();await expect(page).toHaveURL(href);await expect(cards(page)).toHaveCount(1);
  expect((await control(request,'discovery_ai_stats')).calls).toBe(0);
});

test('v2 unwatched 41 to 40 shrink uses replace and preserves the latest draft',async({page,request})=>{
  for(const [title,id] of Object.entries(ids))if(title.startsWith('Search Page'))
    expect((await request.put(`${backend}/films/${id}/profile-state`,{data:{watched:false}})).ok()).toBeTruthy();
  await page.goto('/en/explore');await submit(page,'unwatched films in 2099 newest first');
  await expect(cards(page)).toHaveCount(40);await page.getByRole('button',{name:'Next',exact:true}).click();
  await expect.poll(()=>new URL(page.url()).searchParams.get('offset')).toBe('40');await expect(cards(page)).toHaveCount(1);
  const before=page.url(),history=await page.evaluate(()=>window.history.length);
  await input(page).fill('keep this draft');
  const trigger=cards(page).first();await trigger.click();
  await page.locator('.library-card-media').filter({has:trigger}).getByRole('button',{name:en.Library.markWatched,exact:true}).click();
  await expect.poll(()=>new URL(page.url()).searchParams.has('offset')).toBe(false);await expect(cards(page)).toHaveCount(40);
  await expect(page.locator('#explore-results-title')).toHaveText('40 Films');
  expect(new URL(page.url()).searchParams.get('p')).toBe(new URL(before).searchParams.get('p'));
  expect(await page.evaluate(()=>window.history.length)).toBe(history);await expect(input(page)).toHaveValue('keep this draft');
  expect((await control(request,'discovery_ai_stats')).calls).toBe(0);
});

test('v2 delayed save waits for a newer viewing query already in flight',async({page,request})=>{
  for(const name of ['Search Alpha','Search Beta'])await request.put(`${backend}/films/${ids[name]}/profile-state`,{data:{watched:false}});
  await page.goto('/en/explore');await submit(page,'unwatched films in 2098');await expect(cards(page)).toHaveCount(2);
  let releasePut!:()=>void,releaseFilter!:()=>void,putSeen!:()=>void,filterSeen!:()=>void;
  const putGate=new Promise<void>(r=>{releasePut=r;}),filterGate=new Promise<void>(r=>{releaseFilter=r;});
  const putReceived=new Promise<void>(r=>{putSeen=r;}),filterReceived=new Promise<void>(r=>{filterSeen=r;});
  await page.route('**/api/films/*/profile-state',async route=>{
    if(route.request().method()!=='PUT'){await route.continue();return;}putSeen();await putGate;await route.continue();
  });
  await page.route('**/en/explore/search?**',async route=>{
    const p=new URL(route.request().url()).searchParams.get('p');
    if(route.request().headers().rsc!=='1'||!p||JSON.parse(p).view!=='watched'){await route.continue();return;}
    const response=await route.fetch();filterSeen();await filterGate;await route.fulfill({response}).catch(()=>{});
  });
  try{
    const trigger=page.locator('#film-link-'+ids['Search Alpha']);await trigger.click();
    await page.locator('.library-card-media').filter({has:trigger}).getByRole('button',{name:en.Library.markWatched,exact:true}).click();await putReceived;
    await input(page).fill('newer draft stays here');
    const history=await page.evaluate(()=>window.history.length);
    const click=page.getByRole('group',{name:en.Explore.viewLabel,exact:true}).getByRole('button',{name:'Watched',exact:true}).click();await filterReceived;
    releasePut();await expect.poll(async()=>(await read(request,`/films/${ids['Search Alpha']}/profile-state`)).watched).toBe(true);
    await expect(trigger.getByLabel(en.Library.watched,{exact:true})).toHaveCount(1);
    releaseFilter();await click;await expect(cards(page)).toHaveCount(1);
    await expect(page.locator('#explore-results-title')).toHaveText('1 Film');
    expect(JSON.parse(new URL(page.url()).searchParams.get('p')!).view).toBe('watched');
    expect(JSON.parse(new URL(page.url()).searchParams.get('p')!).year_min).toBe(2098);
    expect(await page.evaluate(()=>window.history.length)).toBe(history+1);
    await expect(input(page)).toHaveValue('newer draft stays here');
    expect((await control(request,'discovery_ai_stats')).calls).toBe(0);
  }finally{releasePut();releaseFilter();}
});

for(const returning of ['browser','page'])test('v2 delayed save then detail '+returning+' return never restores stale results',async({page,request})=>{
  for(const name of ['Search Alpha','Search Beta'])await request.put(`${backend}/films/${ids[name]}/profile-state`,{data:{watched:false}});
  await page.goto('/en/explore');await submit(page,'unwatched films in 2098');await expect(cards(page)).toHaveCount(2);
  const href=page.url();let release!:()=>void,seen!:()=>void,done!:()=>void;
  const gate=new Promise<void>(r=>{release=r;}),received=new Promise<void>(r=>{seen=r;}),delivered=new Promise<void>(r=>{done=r;});
  await page.route('**/api/films/*/profile-state',async route=>{
    if(route.request().method()!=='PUT'){await route.continue();return;}
    const response=await route.fetch();seen();await gate;await route.fulfill({response}).catch(()=>{});done();
  });
  try{
    const trigger=page.locator('#film-link-'+ids['Search Alpha']);await trigger.click();
    await page.locator('.library-card-media').filter({has:trigger}).getByRole('button',{name:en.Library.markWatched,exact:true}).click();await received;
    await page.locator('.library-card-title').filter({hasText:'Search Beta'}).click();
    await expect(page.getByRole('button',{name:en.FilmDetail.return,exact:true})).toBeVisible();
    release();await delivered;
    if(returning==='browser')await page.goBack();
    else await page.getByRole('button',{name:en.FilmDetail.return,exact:true}).click();
    await expect(page).toHaveURL(href);await expect(cards(page)).toHaveCount(1);
    await expect(page.locator('#film-link-'+ids['Search Beta'])).toBeVisible();
    await expect(input(page)).toHaveValue('unwatched films in 2098');
    expect((await control(request,'discovery_ai_stats')).calls).toBe(0);
  }finally{release();}
});
