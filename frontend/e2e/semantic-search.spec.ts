import { test, expect, type APIRequestContext, type Page } from '@playwright/test';
import path from 'node:path';
import en from '../messages/en.json';
import zh from '../messages/zh.json';

const backend=process.env.E2E_BACKEND!;
const cards=(page:Page)=>page.locator('[id^="film-link-"]');
const questions={en:'films about a family reunion',zh:'关于家庭团聚的电影'};
const field=(page:Page,locale='en')=>page.getByRole('searchbox',{name:(locale==='zh'?zh:en).Discovery.label,exact:true});
async function control(request:APIRequestContext,action:string,extra:object={}){
  const response=await request.post(`${backend}/__e2e/control`,{headers:{'x-e2e-token':process.env.E2E_TOKEN!},data:{action,...extra}});
  expect(response.ok()).toBeTruthy();return response.json();
}
async function submit(page:Page,question:string,locale='en'){
  await field(page,locale).fill(question);await field(page,locale).press('Enter');
  await expect.poll(()=>new URL(page.url()).searchParams.get('semantic_snapshot')).toMatch(/^ds_[a-f0-9]{32}$/);
  await expect(page.getByText((locale==='zh'?zh:en).Discovery.semanticEvaluation,{exact:true})).toBeVisible();
}
test.beforeAll(async({request})=>{
  await control(request,'identity_cleanup');
  const media=path.join(process.env.E2E_ROOT!,'normal/media');
  expect((await request.put(`${backend}/settings/media-dir?media_dir=${encodeURIComponent(media)}`)).ok()).toBeTruthy();
  const scan=await request.post(`${backend}/library/scan?media_dir=${encodeURIComponent(media)}`);
  expect(scan.ok()).toBeTruthy();const {workflow_id}=await scan.json();
  await expect.poll(async()=>{const response=await request.get(`${backend}/workflows/${workflow_id}`);return(await response.json()).status;},{timeout:45000}).toBe('succeeded');
});
test.beforeEach(async({request,context})=>{
  await control(request,'semantic_evaluation',{enabled:true,queries:Object.values(questions)});
  await context.route('**/*',route=>['127.0.0.1','localhost'].includes(new URL(route.request().url()).hostname)?route.continue():route.abort('blockedbyclient'));
});
test.afterEach(async({request})=>{await control(request,'semantic_evaluation',{enabled:false});});
test.afterAll(async({request})=>{await control(request,'identity_cleanup');});

for(const locale of ['en','zh'] as const)for(const width of [1440,320]){
  test(`${locale} semantic results reuse cards and restore query, sort, Return and Back at ${width}px`,async({page,request})=>{
    const copy=locale==='zh'?zh:en;
    await page.setViewportSize({width,height:844});await page.goto(`/${locale}/explore`);
    await submit(page,questions[locale],locale);
    expect(await cards(page).count()).toBeGreaterThan(0);
    const token=new URL(page.url()).searchParams.get('semantic_snapshot');
    const count=(await control(request,'semantic_stats')).calls.length;
    expect(count).toBe(3);
    await page.getByRole('button',{name:copy.Explore.sorts.year,exact:true}).click();
    await expect.poll(()=>new URL(page.url()).searchParams.get('order')).toBe('year');
    await page.reload();await expect(cards(page).first()).toBeVisible();
    expect(new URL(page.url()).searchParams.get('semantic_snapshot')).toBe(token);
    await expect(field(page,locale)).toHaveValue(questions[locale]);
    await page.getByRole('button',{name:copy.Discovery.relevance,exact:true}).click();
    await expect.poll(()=>new URL(page.url()).searchParams.get('order')).toBeNull();
    const before=page.url();
    await page.locator('.library-card-title').first().click();
    await expect(page).toHaveURL(/\/library\/film_[a-f0-9]{32}$/);
    // Native in-page Return uses the remembered source, not just browser Back.
    await page.getByRole('button',{name:copy.FilmDetail.return,exact:true}).click();
    await expect(page).toHaveURL(before);await expect(cards(page).first()).toBeVisible();
    await page.reload();await expect(cards(page).first()).toBeVisible();
    await page.goBack();
    await expect(page).toHaveURL(/\/library\/film_[a-f0-9]{32}$/);
    await expect(page.getByRole('button',{name:copy.FilmDetail.return,exact:true})).toBeVisible();
    await page.goForward();
    await expect(page).toHaveURL(before);
    await expect(cards(page).first()).toBeVisible();
    await expect(page.getByText(copy.Discovery.semanticEvaluation,{exact:true})).toBeVisible();
    await expect(field(page,locale)).toHaveValue(questions[locale]);
    expect((await control(request,'semantic_stats')).calls.length).toBe(count);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
    await page.evaluate(async()=>{await document.fonts.ready;});
    await page.screenshot({path:path.join('e2e-artifacts',`semantic-${locale}-${width}.png`),animations:'disabled'});
  });
}

for(const locale of ['en','zh'] as const)test(`${locale} removing content retains strict SQL results through edits, refresh and Back`,async({page,request})=>{
  const copy=locale==='zh'?zh:en;
  const q=locale==='zh'?'日本电影，关于家庭团聚':'Japanese films about a family reunion';
  await control(request,'semantic_evaluation',{enabled:true,queries:[q]});
  await page.goto(`/${locale}/explore`);await submit(page,q,locale);
  const token=new URL(page.url()).searchParams.get('semantic_snapshot');
  const count=(await control(request,'semantic_stats')).calls.length;
  const remove=page.getByRole('button',{name:copy.Discovery.remove.replace('{condition}',locale==='zh'?'家庭团聚':'a family reunion'),exact:true});
  await expect(remove).toBeVisible();
  await page.getByRole('button',{name:copy.Explore.views.unwatched,exact:true}).click();
  await expect.poll(()=>JSON.parse(new URL(page.url()).searchParams.get('p')!).view).toBe('unwatched');
  expect(new URL(page.url()).searchParams.get('semantic_snapshot')).toBe(token);
  await remove.click();await expect.poll(()=>new URL(page.url()).searchParams.get('semantic_removed')).toBe('1');
  expect(new URL(page.url()).searchParams.get('semantic_snapshot')).toBe(token);
  const plan=JSON.parse(new URL(page.url()).searchParams.get('p')!);
  expect(plan.countries).toEqual(['JP']);expect(plan.view).toBe('unwatched');
  const expected=await request.post(`${backend}/explore/search/query`,{data:{question:'Japanese films',plan,edited:true}});
  const expectedData=await expected.json();expect(expectedData.status).toBe('ready');
  const expectedIds=expectedData.results.items.map((item:{film:{id:string}})=>`film-link-${item.film.id}`).sort();
  expect(expectedIds.length).toBeGreaterThan(0);
  const assertResults=async()=>{
    await expect(cards(page)).toHaveCount(expectedIds.length);
    expect((await cards(page).evaluateAll(nodes=>nodes.map(node=>node.id))).sort()).toEqual(expectedIds);
    await expect(page.getByText(copy.Discovery.semanticEvaluation,{exact:true})).toHaveCount(0);
    await expect(field(page,locale)).toHaveValue(q);
  };
  await assertResults();await page.reload();await assertResults();
  await page.getByRole('button',{name:copy.Explore.sorts.year,exact:true}).click();
  await expect.poll(()=>JSON.parse(new URL(page.url()).searchParams.get('p')!).sort).toBe('year');
  await assertResults();
  const source=page.url();
  await page.locator('.library-card-title').first().click();
  await expect(page).toHaveURL(/\/library\/film_[a-f0-9]{32}$/);
  await page.getByRole('button',{name:copy.FilmDetail.return,exact:true}).click();
  await expect(page).toHaveURL(source);await assertResults();
  await page.goBack();await expect(page).toHaveURL(/\/library\/film_[a-f0-9]{32}$/);
  await page.goBack();await expect(page).toHaveURL(source);await assertResults();
  expect((await control(request,'semantic_stats')).calls.length).toBe(count);
});

for(const missing of ['randomUUID','allEntropy'] as const)test(`HTTP search works when ${missing} is unavailable, including evaluation-disabled mode`,async({page,request})=>{
  const fixture=await control(request,'semantic_evaluation',{enabled:true,queries:[]});
  const film=fixture.films[0];
  await control(request,'semantic_evaluation',{enabled:false});
  await page.addInitScript(value=>{
    Object.defineProperty(window.crypto,'randomUUID',{value:undefined,configurable:true});
    if(value==='allEntropy')Object.defineProperty(window.crypto,'getRandomValues',{value:undefined,configurable:true});
  },missing);
  const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message));
  await page.goto('/en/explore');expect(new URL(page.url()).protocol).toBe('http:');
  expect(await page.evaluate(()=>typeof crypto.randomUUID)).toBe('undefined');
  const submitted=page.waitForRequest(r=>r.url().endsWith('/api/explore/search/interpret'));
  await field(page).fill(film.title);await field(page).press('Enter');
  const body=(await submitted).postDataJSON();
  if(missing==='randomUUID')expect(body.request_id).toMatch(/^rq_[a-f0-9]{32}$/);
  else expect(body.request_id).toBeNull();
  await expect(page.locator(`#film-link-${film.id}`)).toBeVisible();
  expect(errors).toEqual([]);expect((await control(request,'semantic_stats')).calls).toEqual([]);
});

for(const locale of ['en','zh'] as const)test(`${locale} bound-title sort and chip edits return actual films locally`,async({page,request})=>{
  const copy=locale==='zh'?zh:en;
  const fixture=await control(request,'semantic_evaluation',{enabled:true,queries:[]});
  const films=fixture.films as {id:string,title:string,year:number}[];
  // The indexed fixture is capped at 12 films; a same-title Film may be outside
  // that subset. Identity uniqueness is a property of the complete local library.
  const response=await request.get(`${backend}/library/films`);expect(response.ok()).toBeTruthy();
  const library=await response.json() as {id:string,title:string}[];
  const film=films.find(item=>library.filter(other=>other.title===item.title).length===1)!;
  expect(film).toBeTruthy();
  for(const q of locale==='zh'?[`《${film.title}》，2100年以前`,`只找《${film.title}》，不要相似推荐。`]:
    [`"${film.title}", before 2100`,`"${film.title}", exact film only, no substitutes.`]){
    await page.goto(`/${locale}/explore`);await field(page,locale).fill(q);await field(page,locale).press('Enter');
    await expect(cards(page)).toHaveCount(1);await expect(page.locator(`#film-link-${film.id}`)).toBeVisible();
    await page.getByRole('button',{name:copy.Explore.sorts.year,exact:true}).click();
    await expect.poll(()=>JSON.parse(new URL(page.url()).searchParams.get('p')!).sort).toBe('year');
    await expect(cards(page)).toHaveCount(1);await page.reload();await expect(page.locator(`#film-link-${film.id}`)).toBeVisible();
    if(JSON.parse(new URL(page.url()).searchParams.get('p')!).year_max!==null){
      await page.getByRole('button',{name:/2099/}).click();
      await expect.poll(()=>JSON.parse(new URL(page.url()).searchParams.get('p')!).year_max).toBeNull();
      await expect(cards(page)).toHaveCount(1);await expect(page.locator(`#film-link-${film.id}`)).toBeVisible();
    }
    const before=page.url();
    await page.getByRole('button',{name:copy.Discovery.remove.replace('{condition}',film.title),exact:true}).click();
    await expect.poll(()=>cards(page).count()).toBeGreaterThan(1);
    await expect(field(page,locale)).toHaveValue(q);
    await page.goBack();await expect(page).toHaveURL(before);await expect(cards(page)).toHaveCount(1);
    await expect(page.locator(`#film-link-${film.id}`)).toBeVisible();
  }
  expect((await control(request,'semantic_stats')).calls).toEqual([]);
});

test('rerank failure is disclosed and cached fallback never retries on refresh',async({page,request})=>{
  await control(request,'semantic_evaluation',{enabled:true,queries:[questions.en],failure:'rerank'});
  await page.goto('/en/explore');await submit(page,questions.en);
  await expect(page.getByText(en.Discovery.semanticFallback,{exact:true})).toBeVisible();
  const count=(await control(request,'semantic_stats')).calls.length;
  await page.reload();await expect(page.getByText(en.Discovery.semanticFallback,{exact:true})).toBeVisible();
  expect((await control(request,'semantic_stats')).calls.length).toBe(count);
});

test('cancel during Decision prevents embedding, rerank and stale navigation',async({page,request})=>{
  await page.addInitScript(()=>Object.defineProperty(window.crypto,'randomUUID',{value:undefined,configurable:true}));
  await control(request,'semantic_evaluation',{enabled:true,queries:[questions.en],hold:'decision'});
  await page.goto('/en/explore');await field(page).fill(questions.en);await field(page).press('Enter');
  await expect.poll(async()=>(await control(request,'semantic_stats')).calls).toEqual(['decision']);
  const cancelled=page.waitForResponse(r=>r.url().endsWith('/api/explore/search/cancel')&&r.ok());
  await page.getByRole('button',{name:en.Discovery.cancel,exact:true}).click();await cancelled;
  await control(request,'semantic_evaluation',{release:true});
  await expect(field(page)).toBeEnabled();
  await page.waitForTimeout(300);
  expect((await control(request,'semantic_stats')).calls).toEqual(['decision']);
  expect(new URL(page.url()).pathname).toBe('/en/explore');
});

test('stale token preserves text and offers ordinary search without model calls',async({page,request})=>{
  await page.goto('/en/explore');await submit(page,questions.en);
  const before=(await control(request,'semantic_stats')).calls.length;
  const url=new URL(page.url());url.searchParams.set('semantic_snapshot',`ds_${'f'.repeat(32)}`);
  await page.goto(url.href);
  await expect(field(page)).toHaveValue(questions.en);
  await expect(page.getByRole('link',{name:en.Discovery.keywordFallback,exact:true})).toBeVisible();
  expect((await control(request,'semantic_stats')).calls.length).toBe(before);
});

for(const locale of ['en','zh'] as const){
  test(`${locale} bound titles and natural references preserve identity, raw input and exclusions`,async({page,request})=>{
    const copy=locale==='zh'?zh:en;
    const fixture=await control(request,'semantic_evaluation',{enabled:true,queries:[]});
    const films=fixture.films as {id:string,title:string,year:number}[];
    const film=films.find(item=>films.filter(other=>other.title===item.title).length>1)!;
    expect(film).toBeTruthy();
    const literal=locale==='zh'?`请帮我找《${film.title}》。`:`Find the film ${film.title}.`;
    const reference=locale==='zh'?`我喜欢《${film.title}》的家庭主题，找其他电影。`:`I enjoyed "${film.title}". What else can I watch?`;
    const unsupported=locale==='zh'?'关于没有暴力的家庭':'films about family with no violence';
    await control(request,'semantic_evaluation',{enabled:true,queries:[literal,reference,unsupported]});
    await page.goto(`/${locale}/explore`);
    await field(page,locale).fill(literal);await field(page,locale).press('Enter');
    await expect(page.locator(`#film-link-${film.id}`)).toBeVisible();
    await expect(field(page,locale)).toHaveValue(literal);
    await page.reload();await expect(page.locator(`#film-link-${film.id}`)).toBeVisible();
    expect((await control(request,'semantic_stats')).calls).toEqual([]);
    await submit(page,reference,locale);
    await expect(page.getByRole('heading',{name:copy.Discovery.chooseReference,exact:true})).toBeVisible();
    expect((await control(request,'semantic_stats')).calls).toEqual([]);
    await page.reload();
    await page.getByRole('button',{name:`${film.title} (${film.year})`,exact:true}).click();
    await expect(cards(page).first()).toBeVisible();
    await expect(page.locator(`#film-link-${film.id}`)).toHaveCount(0);
    const calls=(await control(request,'semantic_stats')).calls;
    expect(calls).toEqual(['rerank']);
    const source=page.url();
    await page.locator('.library-card-title').first().click();
    await expect(page).toHaveURL(/\/library\/film_[a-f0-9]{32}$/);
    await page.getByRole('button',{name:copy.FilmDetail.return,exact:true}).click();
    await expect(page).toHaveURL(source);await page.reload();
    await expect(cards(page).first()).toBeVisible();
    await expect(page.locator(`#film-link-${film.id}`)).toHaveCount(0);
    expect((await control(request,'semantic_stats')).calls).toEqual(calls);
    await field(page,locale).fill(unsupported);await field(page,locale).press('Enter');
    await expect(page.getByText(copy.Discovery.reasons.unsupported_content_negation,{exact:true})).toBeVisible();
    expect((await control(request,'semantic_stats')).calls).toEqual(calls);
  });
}
