import { test, expect, type APIRequestContext, type Page } from '@playwright/test';
import path from 'node:path';
import en from '../messages/en.json';
import zh from '../messages/zh.json';

const backend=process.env.E2E_BACKEND!;
const cards=(page:Page)=>page.locator('[id^="film-link-"]');
const plan={genre:null,person:null,person_role:'any',country:'JP',decade:null,view:'all',sort:'title',direction:'asc'};
async function capture(page:Page,name:string){
  await page.evaluate(async()=>{await document.fonts.ready;await Promise.all([...document.images].map(i=>i.decode().catch(()=>{})));});
  await page.screenshot({path:path.join('e2e-artifacts',name),animations:'disabled'});
}
async function read(request:APIRequestContext,url:string){const r=await request.get(`${backend}${url}`);expect(r.ok()).toBeTruthy();return r.json();}
async function control(request:APIRequestContext,action:string,extra:object={}){
  const r=await request.post(`${backend}/__e2e/control`,{headers:{'x-e2e-token':process.env.E2E_TOKEN!},data:{action,...extra}});expect(r.ok()).toBeTruthy();return r.json();
}
function input(page:Page,locale='en'){return page.getByRole('searchbox',{name:(locale==='zh'?zh:en).Discovery.label,exact:true});}
async function submit(page:Page,q:string,locale='en'){
  const field=input(page,locale);await expect(field).toBeEnabled();await field.fill(q);
  const response=page.waitForResponse(r=>r.url().endsWith('/api/explore/search/interpret')&&r.request().method()==='POST'&&r.request().postDataJSON().question===q);
  await field.press('Enter');const resolved=await(await response).json();
  await expect.poll(()=>new URL(page.url()).searchParams.get('q')).toBe(q);
  await expect.poll(()=>{const p=new URL(page.url()).searchParams;return p.get('p')??p.get('state')??'keyword';}).toBe(resolved.plan?JSON.stringify(resolved.plan):resolved.status==='keyword'?'keyword':resolved.status);
}
test.beforeAll(async({request})=>{
  await control(request,'identity_cleanup');
  const media=path.join(process.env.E2E_ROOT!,'normal/media');
  expect((await request.put(`${backend}/settings/media-dir?media_dir=${encodeURIComponent(media)}`)).ok()).toBeTruthy();
  const scan=await request.post(`${backend}/library/scan?media_dir=${encodeURIComponent(media)}`);expect(scan.ok()).toBeTruthy();const {workflow_id}=await scan.json();
  await expect.poll(async()=>(await read(request,`/workflows/${workflow_id}`)).status,{timeout:45000}).toBe('succeeded');
  await control(request,'library_filter_fixture');
});
test.beforeEach(async({context,request})=>{
  await control(request,'discovery_ai',{enabled:false});
  await context.route('**/*',route=>['127.0.0.1','localhost'].includes(new URL(route.request().url()).hostname)?route.continue():route.abort('blockedbyclient'));
});
test.afterEach(async({request})=>{await control(request,'discovery_ai',{enabled:false});});
test.afterAll(async({request})=>{await control(request,'identity_cleanup');});

for(const locale of ['en','zh'])for(const width of [1440,320]){
  test(`${locale} unified home, local suggestions, IME and keyword results at ${width}px`,async({page,request})=>{
    const copy=locale==='zh'?zh:en;await page.setViewportSize({width,height:844});
    await control(request,'discovery_ai',{enabled:true});
    const posts:string[]=[];page.on('request',r=>{if(r.method()==='POST'&&r.url().includes('/explore/search/interpret'))posts.push(r.url());});
    await page.goto(`/${locale}/explore`);await expect(input(page,locale)).toBeEnabled();
    await capture(page,`discovery-home-${locale}-${width}.png`);
    await expect(page.locator('#ask-form')).toHaveCount(0);await expect(page.locator('#explore-results-title')).toHaveCount(0);
    await input(page,locale).fill('Director');
    await expect(page.getByText(copy.Discovery.suggestions,{exact:true})).toBeVisible();
    expect((await read(request,'/explore/facets/person?q=Director')).total).toBeGreaterThan(0);
    await input(page,locale).dispatchEvent('compositionstart');await input(page,locale).fill('日本');await input(page,locale).press('Enter');
    expect(posts).toEqual([]);await expect(page).toHaveURL(new RegExp(`/explore$`));
    await input(page,locale).dispatchEvent('compositionend');
    await submit(page,'Orbit',locale);
    await expect(page.locator('#search-films-title')).toBeVisible();await expect(cards(page)).toHaveCount(5);
    expect((await control(request,'discovery_ai_stats')).calls).toBe(0);
    await expect(input(page,locale)).toHaveValue('Orbit');
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.getByRole('button',{name:copy.Discovery.clear,exact:true}).click();
    await expect(page).toHaveURL(new RegExp(`/explore$`));await expect(page.locator('#search-films-title')).toHaveCount(0);
    await page.goto(`/${locale}/ask`);await expect(page).toHaveURL(new RegExp(`/explore$`));
    await page.getByRole('button',{name:copy.Navigation.menu,exact:true}).click();
    await expect(page.getByRole('link',{name:copy.Navigation.ask,exact:true})).toHaveCount(0);await page.keyboard.press('Escape');
  });
  test(`${locale} complete rules run directly, chips correct locally and Return restores conditions at ${width}px`,async({page,request})=>{
    const copy=locale==='zh'?zh:en;await page.setViewportSize({width,height:844});await page.goto(`/${locale}/explore`);
    const q=locale==='zh'?'日本电影':'Japanese films';await submit(page,q,locale);
    await expect(page.locator('#explore-results-title')).toHaveText(/^2\b/);await expect(cards(page)).toHaveCount(2);
    await expect(page.getByRole('heading',{name:copy.Discovery.conditions,exact:true})).toBeVisible();
    await capture(page,`discovery-results-${locale}-${width}.png`);
    await expect(page.getByRole('button',{name:copy.Ask.search,exact:true})).toHaveCount(0);
    const href=page.url();const link=page.locator('.library-card-title').first();await link.scrollIntoViewIfNeeded();await link.click();
    await expect(page.getByRole('button',{name:copy.Diary.watchToday,exact:true})).toBeVisible();
    await page.getByRole('button',{name:copy.FilmDetail.return,exact:true}).click();
    await expect(page).toHaveURL(href);await expect(input(page,locale)).toHaveValue(q);await expect(cards(page)).toHaveCount(2);
    const chip=page.locator('[aria-labelledby="discovery-conditions-title"] button').first();await chip.click();
    await expect.poll(()=>new URL(page.url()).searchParams.get('edited')).toBe('1');
    await expect(page.getByRole('heading',{name:copy.Discovery.adjusted,exact:true})).toBeVisible();
    await expect.poll(()=>cards(page).count()).toBe(40);
    await page.reload();await expect(input(page,locale)).toHaveValue(q);await expect(cards(page)).toHaveCount(40);
    await page.goBack();await expect(page).toHaveURL(href);await expect(cards(page)).toHaveCount(2);
    expect((await control(request,'discovery_ai_stats')).calls).toBe(0);
  });
  test(`${locale} unsupported and no-key preserve input with explicit keyword fallback at ${width}px`,async({page,request})=>{
    const copy=locale==='zh'?zh:en;await page.setViewportSize({width,height:844});await page.goto(`/${locale}/explore`);
    const q=locale==='zh'?'未看日本治愈电影':'unwatched Japanese films similar to Alpha';await submit(page,q,locale);
    await expect(page.getByRole('heading',{name:copy.Discovery.states.unsupported,exact:true})).toBeVisible();
    await capture(page,`discovery-unsupported-${locale}-${width}.png`);
    await expect(page.locator('#explore-results-title')).toHaveCount(0);await expect(input(page,locale)).toHaveValue(q);
    await page.getByRole('link',{name:copy.Discovery.keywordFallback,exact:true}).click();
    await expect.poll(()=>new URL(page.url()).searchParams.get('mode')).toBe('keyword');
    await expect(page.getByText(copy.Discovery.keywordOnly,{exact:true})).toBeVisible();
    await submit(page,'Japanese films featuring Director 4',locale);
    await expect(page.getByRole('heading',{name:copy.Discovery.states.unavailable,exact:true})).toBeVisible();
    await expect(page.getByText(copy.Discovery.reasons.ask_not_configured,{exact:true})).toBeVisible();
    await expect(input(page,locale)).toHaveValue('Japanese films featuring Director 4');
    expect((await control(request,'discovery_ai_stats')).calls).toBe(0);
  });
}

for(const locale of ['en','zh']){
  test(locale+' multiple values explain available recovery without retired Explore filters',async({page,request})=>{
    const copy=locale==='zh'?zh:en;
    const question=locale==='zh'?'日本恐怖剧情电影':'Japanese horror drama films';
    await page.setViewportSize({width:320,height:844});await page.goto('/'+locale+'/explore');
    await submit(page,question,locale);
    await expect(page.getByRole('heading',{name:copy.Discovery.states.unsupported,exact:true})).toBeVisible();
    const guidance=page.getByText(copy.Discovery.reasons.multiple_values,{exact:true});
    await expect(guidance).toBeVisible();await expect(guidance).not.toContainText(/combined filters|组合筛选/i);
    await expect(input(page,locale)).toHaveValue(question);await expect(page.locator('#explore-results-title')).toHaveCount(0);
    await expect(page.locator('a[href*="/explore/filter"]')).toHaveCount(0);
    const fallback=page.getByRole('link',{name:copy.Discovery.keywordFallback,exact:true});await expect(fallback).toBeVisible();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await capture(page,`discovery-multiple-values-${locale}-320.png`);
    await fallback.click();await expect.poll(()=>new URL(page.url()).searchParams.get('mode')).toBe('keyword');
    await expect(page.getByText(copy.Discovery.keywordOnly,{exact:true})).toBeVisible();await expect(input(page,locale)).toHaveValue(question);
    await submit(page,locale==='zh'?'日本电影':'Japanese films',locale);
    await expect(cards(page)).toHaveCount(2);
    expect((await control(request,'discovery_ai_stats')).calls).toBe(0);
  });

  test(locale+' explicit find commands hit titles and people while retaining original text without inference',async({page,request})=>{
    await control(request,'discovery_ai',{enabled:true});await page.goto('/'+locale+'/explore');
    const title=locale==='zh'?'找Orbit':'find Orbit';await submit(page,title,locale);
    await expect(cards(page)).toHaveCount(5);await expect(input(page,locale)).toHaveValue(title);
    await page.reload();await expect(cards(page)).toHaveCount(5);await expect(input(page,locale)).toHaveValue(title);
    const person=locale==='zh'?'找Director 4':'find Director 4';await submit(page,person,locale);
    await expect(page.locator('[aria-labelledby="search-people-title"]').getByText('Director 4',{exact:true})).toBeVisible();
    await expect(input(page,locale)).toHaveValue(person);
    await page.goBack();await expect(cards(page)).toHaveCount(5);await expect(input(page,locale)).toHaveValue(title);
    expect((await control(request,'discovery_ai_stats')).calls).toBe(0);
  });
  test(locale+' unsupported roles stay blocked and language filters never substitute country facts',async({page,request})=>{
    const copy=locale==='zh'?zh:en;await control(request,'discovery_ai',{enabled:true});
    await page.goto('/'+locale+'/explore');
    const questions=locale==='zh'?['由Director 4监制并执导的日本电影','由Director 4编剧的日本电影']:
      ['films produced by Director 4','films produced and directed by Director 4'];
    for(const question of questions){
      await submit(page,question,locale);
      await expect(page.getByRole('heading',{name:copy.Discovery.states.unsupported,exact:true})).toBeVisible();
      await expect(page.locator('#explore-results-title')).toHaveCount(0);await expect(input(page,locale)).toHaveValue(question);
    }
    const languages=locale==='zh'?['日语电影','法语电影']:['films in French','movies in Japanese'];
    for(const question of languages){
      await submit(page,question,locale);
      const applied=JSON.parse(new URL(page.url()).searchParams.get('p')!);
      expect(applied.countries).toEqual([]);expect(applied.people).toEqual([]);
      expect(applied.languages).toEqual([{kind:'spoken',exclude:false,
        code:question.includes('French')||question.includes('法语')?'fr':'ja'}]);
      await expect(page.getByText(copy.Discovery.languageUnknown,{exact:true})).toBeVisible();
      await expect(cards(page)).toHaveCount(0);
      await expect(page.getByRole('heading',{name:copy.Discovery.states.unsupported,exact:true})).toHaveCount(0);
    }
    await submit(page,'films produced in Japan',locale);await expect(cards(page)).toHaveCount(2);
    expect((await control(request,'discovery_ai_stats')).calls).toBe(0);
  });
  test(locale+' private absolute and relative paths stay in the input and never reach model transport',async({page,request})=>{
    const copy=locale==='zh'?zh:en;await control(request,'discovery_ai',{enabled:true});await page.goto('/'+locale+'/explore');
    await expect(input(page,locale)).toBeEnabled();const home=page.url();
    const posts:string[]=[];page.on('request',r=>{if(r.method()==='POST'&&r.url().includes('/explore/search/interpret'))posts.push(r.url());});
    for(const path of ['~/Movies/private.mkv','./Movies/private.mkv','/private.mkv','../Movies/private.mkv','.\\Movies\\private.mkv','\\private.mkv','Movies/private.mkv','Movies\\private.mkv','Movies/private film.mkv','Movies\\private film.mkv',"'Movies/My Private Film.mkv'","\u0060/private.mkv\u0060","\u0060~/Movies/private.mkv\u0060","\u0060./Movies/private.mkv\u0060",
      'Movies//My Private Film.mkv','Movies///My Private Film.mkv','Movies'+'\\'.repeat(2)+'My Private Film.mkv',
      'Movies/\\My Private Film.mkv','Movies\\/My Private Film.mkv',"'My Movies//私人的电影.mkv'"]){
      const question='Japanese films featuring '+path;await input(page,locale).fill(question);await input(page,locale).press('Enter');
      await expect(page.getByRole('alert').filter({hasText:copy.Discovery.reasons.ask_private_input})).toBeVisible();
      await expect(input(page,locale)).toHaveValue(question);await expect(page).toHaveURL(home);
      await expect(page.locator('#explore-results-title')).toHaveCount(0);
      const response=await request.post(backend+'/explore/search/interpret',{data:{question,allow_ai:true,locale}});
      expect(response.status()).toBe(422);expect((await response.json()).detail.code).toBe('ask_private_input');
    }
    expect(posts).toEqual([]);expect((await control(request,'discovery_ai_stats')).calls).toBe(0);
  });
}

test('AI is called once on submission; reload, condition edits, Back and errors never retry inference',async({page,request})=>{
  await control(request,'discovery_ai',{enabled:true,reply:{status:'ready',plan:{...plan,person:'Director 4'},confidence:.99,unhandled:[]}});
  await page.goto('/en/explore');await submit(page,'Japanese films featuring Director 4');
  await expect.poll(()=>new URL(page.url()).searchParams.get('source')).toBe('ai');
  await expect(page.locator('#explore-results-title')).toBeVisible();
  expect((await control(request,'discovery_ai_stats')).calls).toBe(1);
  const href=page.url();await page.reload();await expect(input(page)).toHaveValue('Japanese films featuring Director 4');
  await page.getByRole('button',{name:'Year',exact:true}).click();await expect.poll(()=>new URL(page.url()).searchParams.get('edited')).toBe('1');
  await page.goBack();await expect(page).toHaveURL(href);
  expect((await control(request,'discovery_ai_stats')).calls).toBe(1);
  await control(request,'discovery_ai',{enabled:true,failure:'timeout'});
  await submit(page,'Japanese films featuring Actor 4');
  await expect(page.getByText(en.Discovery.reasons.ask_timeout,{exact:true})).toBeVisible();
  await page.reload();await expect(page.getByText(en.Discovery.reasons.ask_timeout,{exact:true})).toBeVisible();
  expect((await control(request,'discovery_ai_stats')).calls).toBe(1);
});

test('low-confidence and malicious model plans never execute partial filters',async({page,request})=>{
  await page.goto('/en/explore');
  for(const reply of [{status:'ready',plan:{...plan,person:'Director 4'},confidence:.4,unhandled:[]},
    {status:'ready',plan:{...plan,sql:'DELETE'},confidence:.99,unhandled:[]},
    {status:'ready',plan,confidence:.99,unhandled:[]}]){
    await control(request,'discovery_ai',{enabled:true,reply});await submit(page,'Japanese films featuring Director 4');
    await expect(page.locator('#explore-results-title')).toHaveCount(0);
    await expect(page.getByRole('link',{name:en.Discovery.keywordFallback,exact:true})).toBeVisible();
    expect((await control(request,'discovery_ai_stats')).calls).toBe(1);
  }
});

test('new submit and cancel ignore a delayed older interpretation',async({page,request})=>{
  await control(request,'discovery_ai',{enabled:true,reply:{status:'ready',plan:{...plan,person:'Director 4'},confidence:.99,unhandled:[]}});
  let release!:()=>void;const held=new Promise<void>(resolve=>{release=resolve;});
  let reached!:()=>void;const received=new Promise<void>(resolve=>{reached=resolve;});
  await page.route('**/api/explore/search/interpret',async route=>{
    if(route.request().postDataJSON().question!=='Japanese films featuring Director 4'){await route.continue();return;}
    const response=await route.fetch();reached();await held;await route.fulfill({response}).catch(()=>{});
  });
  await page.goto('/en/explore');await input(page).fill('Japanese films featuring Director 4');await input(page).press('Enter');await received;
  await page.getByRole('button',{name:en.Discovery.cancel,exact:true}).click();
  await submit(page,'Orbit');await expect(cards(page)).toHaveCount(5);const href=page.url();release();
  await expect(page).toHaveURL(href);await expect(input(page)).toHaveValue('Orbit');
  expect((await control(request,'discovery_ai_stats')).calls).toBe(1);
});

test('unwatched search shrinks 41 to 40 with replace, preserving text, sorting and history',async({page,request})=>{
  const all=await read(request,'/explore/films?decade=1980&limit=100');
  expect(all.total).toBe(42);
  for(const {film} of all.items)expect((await request.put(`${backend}/films/${film.id}/profile-state`,{data:{watched:false}})).ok()).toBeTruthy();
  expect((await request.put(`${backend}/films/${all.items[0].film.id}/profile-state`,{data:{watched:true}})).ok()).toBeTruthy();
  await page.goto('/en/explore');const q='unwatched films from the 1980s newest first';await submit(page,q);
  await page.getByRole('button',{name:'Next',exact:true}).click();
  await expect.poll(()=>new URL(page.url()).searchParams.get('offset')).toBe('40');await expect(cards(page)).toHaveCount(1);
  const before=page.url(),history=await page.evaluate(()=>window.history.length);
  await input(page).fill('retained draft');
  const trigger=cards(page).first();await trigger.click();
  await page.locator('.library-card-media').filter({has:trigger}).getByRole('button',{name:en.Library.markWatched,exact:true}).click();
  await expect.poll(()=>new URL(page.url()).searchParams.has('offset')).toBe(false);
  await expect(cards(page)).toHaveCount(40);await expect(page.locator('#explore-results-title')).toHaveText('40 Films');
  expect(new URL(page.url()).searchParams.get('p')).toBe(new URL(before).searchParams.get('p'));
  await expect(input(page)).toHaveValue('retained draft');
  expect(await page.evaluate(()=>window.history.length)).toBe(history);
  expect((await control(request,'discovery_ai_stats')).calls).toBe(0);
});

test('a newer submit survives an older result navigation pending',async({page,request})=>{
  let release!:()=>void;const held=new Promise<void>(resolve=>{release=resolve;});
  let reached!:()=>void;const received=new Promise<void>(resolve=>{reached=resolve;});
  await page.route('**/en/explore/search?**',async route=>{
    const url=new URL(route.request().url());
    if(url.searchParams.get('q')!=='Orbit'||route.request().headers().rsc!=='1'){await route.continue();return;}
    const response=await route.fetch();reached();await held;await route.fulfill({response}).catch(()=>{});
  });
  await page.goto('/en/explore');await input(page).fill('Orbit');await input(page).press('Enter');await received;
  await submit(page,'Japanese films');release();
  await expect(page.locator('#explore-results-title')).toHaveText(/^2\b/);
  await expect(input(page)).toHaveValue('Japanese films');
  expect((await control(request,'discovery_ai_stats')).calls).toBe(0);
});

test('outgoing collection navigation wins over a delayed interpretation before navigation commits',async({page,request})=>{
  await control(request,'discovery_ai',{enabled:true,reply:{status:'ready',plan:{...plan,person:'Director 4'},confidence:.99,unhandled:[]}});
  let releaseAI!:()=>void,releaseDirectory!:()=>void,seenAI!:()=>void,seenDirectory!:()=>void,delivered!:()=>void;
  const aiGate=new Promise<void>(r=>{releaseAI=r;}),dirGate=new Promise<void>(r=>{releaseDirectory=r;});
  const aiSeen=new Promise<void>(r=>{seenAI=r;}),dirSeen=new Promise<void>(r=>{seenDirectory=r;}),aiDone=new Promise<void>(r=>{delivered=r;});
  await page.route('**/api/explore/search/interpret',async route=>{const response=await route.fetch();seenAI();await aiGate;await route.fulfill({response}).catch(()=>{});delivered();});
  await page.route('**/en/explore?**',async route=>{
    if(route.request().headers().rsc!=='1'||new URL(route.request().url()).searchParams.get('category')!=='country'){await route.continue();return;}
    const response=await route.fetch();seenDirectory();await dirGate;await route.fulfill({response}).catch(()=>{});
  });
  await page.goto('/en/explore');await input(page).fill('Japanese films featuring Director 4');await input(page).press('Enter');await aiSeen;
  const click=page.getByRole('navigation',{name:en.Collections.categoryLabel,exact:true}).getByRole('link',{name:new RegExp('^'+en.Collections.categories.country)}).click();await dirSeen;
  releaseAI();await aiDone;expect(new URL(page.url()).pathname).toBe('/en/explore');
  releaseDirectory();await click;await expect.poll(()=>new URL(page.url()).searchParams.get('category')).toBe('country');await expect(page.locator('h1')).toHaveText(en.Collections.homeTitle);
  expect((await control(request,'discovery_ai_stats')).calls).toBe(1);
});

for(const locale of ['en','zh'])test(`${locale} only real Person ambiguity asks for a choice, with no manual form or confirmation`,async({page,request})=>{
  const copy=locale==='zh'?zh:en;await control(request,'discovery_ambiguity',{enabled:true});
  try{
    await page.goto(`/${locale}/explore`);await submit(page,'films starring Duplicate Person',locale);
    await expect(page.getByRole('heading',{name:copy.Discovery.states.needs_clarification,exact:true})).toBeVisible();
    const choices=page.getByRole('button',{name:/^Duplicate Person/});await expect(choices).toHaveCount(2);
    await expect(page.locator('#explore-results-title')).toHaveCount(0);await expect(page.locator('#ask-form')).toHaveCount(0);
    await capture(page,`discovery-ambiguity-${locale}.png`);
    await choices.first().click();await expect.poll(()=>new URL(page.url()).searchParams.get('person_id')).not.toBeNull();
    await expect(page.locator('#explore-results-title')).toBeVisible();
    expect((await control(request,'discovery_ai_stats')).calls).toBe(0);
  }finally{await control(request,'discovery_ambiguity',{enabled:false});}
});

test('a save finishing during a newer viewing filter refreshes that latest result without inference',async({page,request})=>{
  const jp=await read(request,'/explore/films?country=JP');
  for(const {film} of jp.items)expect((await request.put(`${backend}/films/${film.id}/profile-state`,{data:{watched:false}})).ok()).toBeTruthy();
  await page.goto('/en/explore');await submit(page,'unwatched Japanese films');await expect(cards(page)).toHaveCount(2);
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
  const trigger=cards(page).first();const id=await trigger.getAttribute('id');await trigger.click();
  await page.locator('.library-card-media').filter({has:trigger}).getByRole('button',{name:en.Library.markWatched,exact:true}).click();await putReceived;
  await input(page).fill('preserved newer draft');
  const filter=page.getByRole('group',{name:en.Explore.viewLabel,exact:true}).getByRole('button',{name:'Watched',exact:true}).click();await filterReceived;
  const history=await page.evaluate(()=>window.history.length);releasePut();
  await expect.poll(async()=>(await read(request,`/films/${id!.slice('film-link-'.length)}/profile-state`)).watched).toBe(true);
  await expect(trigger.getByLabel(en.Library.watched,{exact:true})).toHaveCount(1);
  releaseFilter();await filter;
  await expect(page.locator('#explore-results-title')).toHaveText('1 Film');await expect(cards(page)).toHaveCount(1);
  expect(JSON.parse(new URL(page.url()).searchParams.get('p')!).view).toBe('watched');
  await expect(input(page)).toHaveValue('preserved newer draft');
  expect(await page.evaluate(()=>window.history.length)).toBe(history+1);
  expect((await control(request,'discovery_ai_stats')).calls).toBe(0);
});

test('detail write then browser Back refreshes the cached interpreted list without another model request',async({page,request})=>{
  const jp=await read(request,'/explore/films?country=JP');
  for(const {film} of jp.items)expect((await request.put(`${backend}/films/${film.id}/profile-state`,{data:{watched:false}})).ok()).toBeTruthy();
  await page.goto('/en/explore');await submit(page,'unwatched Japanese films');await expect(cards(page)).toHaveCount(2);
  const href=page.url(),link=page.locator('.library-card-title').first();
  const id=(await link.getAttribute('href'))!.split('/').at(-1)!;await link.click();
  await page.getByRole('button',{name:en.Diary.watchToday,exact:true}).click();
  await expect.poll(async()=>(await read(request,`/films/${id}/profile-state`)).watched).toBe(true);
  await page.goBack();await expect(page).toHaveURL(href);await expect(cards(page)).toHaveCount(1);
  await expect(page.locator('#explore-results-title')).toHaveText('1 Film');
  expect((await control(request,'discovery_ai_stats')).calls).toBe(0);
});
