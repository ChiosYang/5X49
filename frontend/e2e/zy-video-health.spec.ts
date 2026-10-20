import { test, expect, type APIRequestContext } from '@playwright/test';
import { writeFile, access, rm } from 'node:fs/promises';
import path from 'node:path';

test.describe.configure({ mode: 'serial' });
const backend = process.env.E2E_BACKEND!;
const endpoint = `${backend}/maintenance/video-health`;
async function control(request: APIRequestContext, action: string) {
  const result = await request.post(`${backend}/__e2e/control`, { headers: { 'x-e2e-token': process.env.E2E_TOKEN! }, data: { action } });
  expect(result.ok()).toBeTruthy(); return result.json();
}
async function status(request: APIRequestContext) { return (await request.get(endpoint)).json(); }

test.beforeAll(async ({ request }) => { await control(request, 'health_fixture'); });
test.beforeEach(async ({ context }) => {
  await context.route('**/*', route => ['127.0.0.1', 'localhost'].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort('blockedbyclient'));
});

test('settings save UTC schedule, one-click durable queue, pause and resume', async ({ page, request }) => {
  await page.goto('/zh/settings?section=library');
  const panel = page.locator('section[aria-labelledby="video-health-settings"]');
  await expect(panel.getByRole('heading', { name: '视频健康检查' })).toBeVisible();
  await panel.getByLabel('允许开始时间（UTC）').fill('00:00');
  await panel.getByLabel('允许结束时间（UTC）').fill('00:00');
  await panel.getByLabel('每日预算（分钟）').fill('5');
  await panel.getByRole('button', { name: '保存调度设置' }).click();
  await expect.poll(async () => (await status(request)).config.daily_budget_minutes).toBe(5);
  await panel.getByRole('button', { name: '一键排队检查片库' }).dblclick();
  await expect.poll(async () => (await status(request)).queue_sweep_pending).toBeTruthy();
  await expect(panel.getByRole('button', { name: '恢复检查' })).toBeVisible();
  await page.screenshot({ path: 'e2e-artifacts/health-settings-mobile-zh.png', fullPage: true });
  await control(request, 'health_allow');
  await panel.getByRole('button', { name: '恢复检查' }).click();
  await expect.poll(async () => (await status(request)).counts.abnormal, { timeout: 30000 }).toBeGreaterThan(0);
  await expect.poll(async () => (await status(request)).counts.passed, { timeout: 30000 }).toBeGreaterThan(0);
  await panel.getByRole('button', { name: '暂停检查' }).click();
  await expect.poll(async () => (await status(request)).config.paused).toBeTruthy();
});

test('maintenance separates quick/deep results, version evidence, unknown location and persistent notice', async ({ page, request }) => {
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.goto('/en/library/manage#video-health');
  const panel = page.locator('#video-health');
  await expect(panel.getByText('The container or decoder reported invalid media data.', { exact: false }).first()).toBeVisible();
  await panel.getByRole('button', { name: 'Inspection details' }).first().click();
  await expect(panel.getByText('Quick container check:', { exact: false })).toBeVisible();
  await expect(panel.getByText('Full audio/video decode:', { exact: false })).toBeVisible();
  await expect(panel.getByText('The exact error time could not be established.')).toBeVisible();
  await expect(panel.getByText('Filesystem version:', { exact: false })).toBeVisible();
  const before = (await status(request)).unread;
  expect(before).toBeGreaterThan(0);
  await page.setViewportSize({ width: 320, height: 844 });
  const navigation = page.locator('nav').first();
  await expect(navigation.getByRole('link', { name: /video version.*attention/ })).toBeVisible();
  const logo = await navigation.getByRole('link', { name: '5X49', exact: true }).boundingBox();
  const search = await navigation.getByRole('button', { name: 'Search', exact: true }).boundingBox();
  expect(logo && search && logo.x + logo.width <= search.x).toBeTruthy();
  await page.setViewportSize({ width: 1440, height: 1100 });
  await panel.getByRole('button', { name: 'Mark notification read' }).click();
  await expect.poll(async () => (await status(request)).unread).toBe(before - 1);
  await page.reload();
  await expect.poll(async () => (await status(request)).unread).toBe(before - 1);
  await panel.getByRole('button', { name: 'Inspection details' }).first().click();
  await expect(panel.getByText('The exact error time could not be established.')).toBeVisible();
  await panel.screenshot({ path: 'e2e-artifacts/health-maintenance-panel-en.png' });
  await page.screenshot({ path: 'e2e-artifacts/health-maintenance-desktop-en.png', fullPage: true });
});

test('file replacement expires old result; cancelling queue does not report damage', async ({ page, request }) => {
  await control(request, 'health_replace');
  await page.goto('/en/library/manage#video-health');
  const panel = page.locator('#video-health');
  await panel.getByLabel('Show results').selectOption('all');
  await panel.getByRole('button', { name: 'Inspection details' }).first().click();
  await expect(panel.getByText('This is an earlier or unavailable file version.', { exact: false })).toBeVisible();
  await page.goto('/en/settings?section=library');
  const settings = page.locator('section[aria-labelledby="video-health-settings"]');
  await settings.getByRole('button', { name: 'Queue library check' }).click();
  await settings.getByRole('button', { name: 'Cancel queued and active checks' }).click();
  await expect.poll(async () => (await status(request)).queue_sweep_pending).toBeFalsy();
  await expect.poll(async () => (await status(request)).config.paused).toBeTruthy();
});

test('backend restart retains queue configuration and old abnormal version notification receipt', async ({ request, page }) => {
  const before = await status(request);
  const root = process.env.E2E_ROOT!;
  await rm(path.join(root, 'restarted'), { force: true });
  await writeFile(path.join(root, 'restart'), 'health restart');
  await expect.poll(async () => { try { await access(path.join(root, 'restarted')); return true; } catch { return false; } }, { timeout: 30000 }).toBeTruthy();
  await expect.poll(async () => (await status(request)).config.daily_budget_minutes).toBe(before.config.daily_budget_minutes);
  expect((await status(request)).unread).toBe(before.unread);
  await page.goto('/zh/settings?section=library');
  await expect(page.locator('section[aria-labelledby="video-health-settings"]').getByRole('button', { name: '恢复检查' })).toBeVisible();
});
