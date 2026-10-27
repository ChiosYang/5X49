import { test, expect, type Page } from '@playwright/test';
import en from '../messages/en.json';
import zh from '../messages/zh.json';
const backend=process.env.E2E_BACKEND!;
const cards=(page:Page)=>page.locator('[id^="film-link-"]');
let ids:Record<string,string>;
async function control(request:import('@playwright/test').APIRequestContext,action:string,extra:object={}){
  const response=await request.post(`${backend}/__e2e/control`,{headers:{'x-e2e-token':process.env.E2E_TOKEN!},data:{action,...extra}});
  expect(response.ok()).toBeTruthy();return response.json();
}
test.beforeAll(async({request})=>{await control(request,'identity_cleanup');ids=await control(request,'enhanced_search_fixture');});
test.beforeEach(async({context,request})=>{
  await control(request,'discovery_ai',{enabled:true});
  await context.route('**/*',route=>['127.0.0.1','localhost'].includes(new URL(route.request().url()).hostname)?route.continue():route.abort('blockedbyclient'));
});
test.afterEach(async({request})=>{await control(request,'discovery_ai',{enabled:false});});
test.afterAll(async({request})=>{await control(request,'identity_cleanup');});
for(const locale of ['en','zh'] as const)for(const width of [1440,320]){
  test(`${locale} language filters preserve source meaning, unknowns, chips and navigation at ${width}px`,async({page,request})=>{
    const copy=locale==='zh'?zh:en;
    await page.setViewportSize({width,height:844});await page.goto(`/${locale}/explore`);
    const input=page.getByRole('searchbox',{name:copy.Discovery.label,exact:true});
    const submit=async(q:string)=>{await expect(input).toBeEnabled();await input.fill(q);await input.press('Enter');await expect.poll(()=>new URL(page.url()).searchParams.get('q')).toBe(q);};
    const question=locale==='zh'?'只看日语电影，2098年':'films in Japanese in 2098';
    await submit(question);await expect(cards(page)).toHaveCount(1);await expect(page.locator('#film-link-'+ids['Search Alpha'])).toBeVisible();
    const href=page.url();
    const label=locale==='zh'?'片中语言：日语':'Spoken language: Japanese';
    await page.getByRole('button',{name:copy.Discovery.remove.replace('{condition}',label),exact:true}).click();
    await expect(cards(page)).toHaveCount(2);
    expect(JSON.parse(new URL(page.url()).searchParams.get('p')!).year_min).toBe(2098);
    await page.reload();await expect(cards(page)).toHaveCount(2);
    await page.goBack();await expect(page).toHaveURL(href);await expect(cards(page)).toHaveCount(1);
    await submit(locale==='zh'?'原始语言为英语的电影':'original language English');
    await expect(cards(page)).toHaveCount(1);await expect(page.locator('#film-link-'+ids['Search Gamma'])).toBeVisible();
    await submit(locale==='zh'?'不要英语电影':'films not in English');
    await expect(cards(page)).toHaveCount(1);await expect(page.locator('#film-link-'+ids['Search Beta'])).toBeVisible();
    await expect(page.getByText(copy.Discovery.languageUnknown,{exact:true})).toBeVisible();
    expect((await control(request,'discovery_ai_stats')).calls).toBe(0);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  });
}
