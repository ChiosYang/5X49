import { test, expect, type APIRequestContext } from '@playwright/test';
import path from 'node:path';
import en from '../messages/en.json';

const backend=process.env.E2E_BACKEND!;
async function control(request:APIRequestContext,action:string,extra:object={}){
  const response=await request.post(`${backend}/__e2e/control`,{headers:{'x-e2e-token':process.env.E2E_TOKEN!},data:{action,...extra}});
  expect(response.ok()).toBeTruthy();return response.json();
}
test('new semantic submission wins while an older native Decision is still in flight',async({page,request,context})=>{
  await context.route('**/*',route=>['127.0.0.1','localhost'].includes(new URL(route.request().url()).hostname)?route.continue():route.abort('blockedbyclient'));
  await control(request,'identity_cleanup');
  const media=path.join(process.env.E2E_ROOT!,'normal/media');
  expect((await request.put(`${backend}/settings/media-dir?media_dir=${encodeURIComponent(media)}`)).ok()).toBeTruthy();
  const scan=await request.post(`${backend}/library/scan?media_dir=${encodeURIComponent(media)}`);expect(scan.ok()).toBeTruthy();
  const {workflow_id}=await scan.json();
  await expect.poll(async()=>{const response=await request.get(`${backend}/workflows/${workflow_id}`);return(await response.json()).status;},{timeout:45000}).toBe('succeeded');
  const old='films about a family reunion',latest='films about a distant spacecraft';
  await control(request,'semantic_evaluation',{enabled:true,queries:[old,latest],hold:'decision'});
  try{
    await page.goto('/en/explore');
    const input=page.getByRole('searchbox',{name:en.Discovery.label,exact:true});
    await input.fill(old);await input.press('Enter');
    await expect.poll(async()=>(await control(request,'semantic_stats')).calls).toEqual(['decision']);
    const cancelled=page.waitForResponse(r=>r.url().endsWith('/api/explore/search/cancel')&&r.ok());
    await input.fill(latest);await cancelled;await input.press('Enter');
    await control(request,'semantic_evaluation',{release:true});
    await expect.poll(()=>new URL(page.url()).searchParams.get('q')).toBe(latest);
    await expect.poll(()=>new URL(page.url()).searchParams.get('semantic_snapshot')).toMatch(/^ds_[a-f0-9]{32}$/);
    await expect(input).toHaveValue(latest);
    await expect(page.getByText(en.Discovery.semanticEvaluation,{exact:true})).toBeVisible();
    expect((await control(request,'semantic_stats')).calls).toEqual(['decision','decision','embedding','rerank']);
  }finally{
    await control(request,'semantic_evaluation',{enabled:false});
    await control(request,'identity_cleanup');
  }
});
