import { test, expect, type APIRequestContext, type Page } from '@playwright/test';
import { access, rm, writeFile } from 'node:fs/promises';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import path from 'node:path';

test.describe.configure({ mode: 'serial' });
const backend = process.env.E2E_BACKEND!;
const root = process.env.E2E_ROOT!;
const endpoint = `${backend}/maintenance/backups`;
const panel = (page: Page) => page.locator('section[aria-labelledby="backup-heading"]');
let filmId: string;
async function control(request: APIRequestContext, action: string) {
  const result = await request.post(`${backend}/__e2e/control`, { headers: { 'x-e2e-token': process.env.E2E_TOKEN! }, data: { action } });
  expect(result.ok()).toBeTruthy(); return result.json();
}
async function status(request: APIRequestContext) { return (await request.get(endpoint)).json(); }
test.beforeAll(async ({ request }) => { filmId = (await control(request, 'backup_fixture')).film_id; });
test.beforeEach(async ({ context }) => {
  await context.route('**/*', route => ['127.0.0.1', 'localhost'].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort('blockedbyclient'));
});

test('one-click archive restores through offline CLI and boots with no task replay; desktop pixels', async ({ page, request }) => {
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.goto('/zh/library/manage');
  await expect(panel(page).getByRole('button', { name: '一键备份下载' })).toBeEnabled();
  const received = page.waitForEvent('download');
  await panel(page).getByRole('button', { name: '一键备份下载' }).click();
  const download = await received;
  const saved = path.join(root, 'browser-backup.zip');
  await download.saveAs(saved);
  expect(await download.failure()).toBeNull();
  await expect.poll(async () => (await status(request)).last_success?.download_triggered_at).toBeTruthy();
  const python = path.resolve('../backend/.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
  const restored = await promisify(execFile)(python, ['-X', 'utf8', path.resolve('e2e/backup_restore.py'), saved, filmId], { timeout: 30000 });
  expect(restored.stdout).toContain('"actual_application_boot": true');
  expect(restored.stdout).toContain('"jobs_executed": 0');
  const report = JSON.parse(restored.stdout.trim().split(/\r?\n/).at(-1)!);
  await writeFile('e2e-artifacts/backup-restore-report.json', JSON.stringify(report, null, 2) + '\n');
  await panel(page).getByText('恢复范围与操作说明').click();
  await page.screenshot({ path: 'e2e-artifacts/backup-desktop-zh.png', fullPage: true });
});

test('lost create response and rapid repeat clicks retain a single generation', async ({ page, request }) => {
  const before = (await control(request, 'backup_receipts')).count;
  await control(request, 'hold_backup');
  await page.goto('/en/library/manage');
  const bodies: string[] = [];
  await page.route('**/api/maintenance/backups', async route => {
    if (route.request().method() !== 'POST') return route.continue();
    bodies.push(route.request().postData()!);
    await route.fetch();
    return route.abort('failed');
  });
  await panel(page).getByRole('button', { name: 'Back up and download' }).dblclick();
  await expect(panel(page).getByText('Could not confirm this request.', { exact: false })).toBeVisible();
  expect(bodies).toHaveLength(1);
  const received = page.waitForEvent('download');
  await control(request, 'release_backup');
  expect(await (await received).failure()).toBeNull();
  expect((await control(request, 'backup_receipts')).count).toBe(before + 1);
});

test('downloading an older success does not discard a pending generation', async ({ page, request }) => {
  await control(request, 'hold_backup');
  await page.goto('/en/library/manage');
  await panel(page).getByRole('button', { name: 'Back up and download' }).click();
  await expect(panel(page).getByRole('button', { name: 'Generating backup…' })).toBeDisabled();
  const id = await page.evaluate(() => sessionStorage.getItem('5x49:pending-backup:v1'));
  const older = page.waitForEvent('download');
  await panel(page).getByRole('button', { name: 'Download again' }).click();
  await older;
  expect(await page.evaluate(() => sessionStorage.getItem('5x49:pending-backup:v1'))).toBe(id);
  const newer = page.waitForEvent('download');
  await control(request, 'release_backup');
  expect((await newer).suggestedFilename()).toContain(id!);
});

test('generation and transfer failures retain previous success and permit retry', async ({ page, request }) => {
  const previous = (await status(request)).last_success.id;
  await control(request, 'fail_backup');
  await page.goto('/en/library/manage');
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/maintenance/backups/*', async route => {
    await held;
    await route.continue().catch(() => {});
  });
  await panel(page).getByRole('button', { name: 'Back up and download' }).click();
  await expect(panel(page).getByText('Backup generation failed.', { exact: false }).first()).toBeVisible();
  expect((await status(request)).last_success.id).toBe(previous);
  await page.route('**/maintenance/backups/*/download', route => route.abort('failed'));
  try {
    await panel(page).getByRole('button', { name: 'Download again' }).click();
    await expect(panel(page).getByText('Download could not be triggered.', { exact: false })).toBeVisible();
  } finally { release(); }
  await expect.poll(() => page.evaluate(() => sessionStorage.getItem('5x49:pending-backup:v1'))).toBeNull();
  await expect(panel(page).getByText('Download could not be triggered.', { exact: false })).toBeVisible();
  await page.unroute('**/api/maintenance/backups/*');
  await page.unroute('**/maintenance/backups/*/download');
  const received = page.waitForEvent('download');
  await panel(page).getByRole('button', { name: 'Download again' }).click();
  expect((await received).suggestedFilename()).toContain(previous);
});

test('server restart marks interrupted generation and keeps the previous archive', async ({ page, request }) => {
  const previous = (await status(request)).last_success.id;
  await control(request, 'hold_backup');
  await page.goto('/en/library/manage');
  await panel(page).getByRole('button', { name: 'Back up and download' }).click();
  await expect(panel(page).getByRole('button', { name: 'Generating backup…' })).toBeDisabled();
  await rm(path.join(root, 'restarted'), { force: true });
  await writeFile(path.join(root, 'restart'), 'backup interruption');
  await expect.poll(async () => { try { await access(path.join(root, 'restarted')); return true; } catch { return false; } }, { timeout: 30000 }).toBe(true);
  const recovered = await status(request);
  expect(recovered.last_attempt.status).toBe('interrupted');
  expect(recovered.last_success.id).toBe(previous);
  await expect(panel(page).getByText('Generation was interrupted.', { exact: false }).first()).toBeVisible();
});

test('expiry, truthful unreadable state and narrow Chinese pixels', async ({ page, request }) => {
  const previous = (await status(request)).last_success.id;
  await control(request, 'expire_backup');
  await page.goto('/en/library/manage');
  await expect(panel(page).getByText('This package has expired,', { exact: false })).toBeVisible();
  await expect(panel(page).getByRole('button', { name: 'Download again' })).toHaveCount(0);
  expect((await request.get(`${endpoint}/${previous}/download`)).status()).toBe(410);
  await page.route('**/api/maintenance/backups', route => route.fulfill({ status: 503, json: { detail: { code: 'backup_storage_unavailable' } } }));
  await page.reload();
  await expect(panel(page).getByText('Backup status is unavailable.', { exact: false })).toBeVisible();
  await expect(panel(page).getByRole('button', { name: 'Back up and download' })).toBeDisabled();
  await page.unroute('**/api/maintenance/backups');
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/zh/library/manage');
  const received = page.waitForEvent('download');
  await panel(page).getByRole('button', { name: '一键备份下载' }).click();
  await received;
  await expect(panel(page).getByRole('button', { name: '重新下载' })).toBeEnabled();
  await panel(page).getByText('恢复范围与操作说明').click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: 'e2e-artifacts/backup-narrow-zh.png', fullPage: true });
});

test('stalled create request times out and retries the same identifier', async ({ page, request }) => {
  const before = (await control(request, 'backup_receipts')).count;
  await page.goto('/en/library/manage');
  await expect(panel(page).getByRole('button', { name: 'Back up and download' })).toBeEnabled();
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/maintenance/backups', async route => {
    if (route.request().method() !== 'POST') return route.continue();
    await held;
    await route.abort('failed').catch(() => {});
  });
  try {
    await panel(page).getByRole('button', { name: 'Back up and download' }).click();
    await expect(panel(page).getByText('Could not confirm this request.', { exact: false })).toBeVisible({ timeout: 20000 });
    await expect(panel(page).getByRole('button', { name: 'Retry same request' })).toBeEnabled();
  } finally { release(); }
  const id = await page.evaluate(() => sessionStorage.getItem('5x49:pending-backup:v1'));
  await page.unroute('**/api/maintenance/backups');
  const received = page.waitForEvent('download');
  await panel(page).getByRole('button', { name: 'Retry same request' }).click();
  expect((await received).suggestedFilename()).toContain(id!);
  expect((await control(request, 'backup_receipts')).count).toBe(before + 1);
});

test('stalled status refresh after successful POST cannot lock generation or download', async ({ page }) => {
  await page.goto('/en/library/manage');
  await expect(panel(page).getByRole('button', { name: 'Back up and download' })).toBeEnabled();
  let release!: () => void, committed = false;
  const held = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/maintenance/backups', async route => {
    if (route.request().method() === 'POST') {
      const response = await route.fetch(); committed = true;
      return route.fulfill({ response });
    }
    if (committed) await held;
    return route.continue();
  });
  try {
    const received = page.waitForEvent('download', { timeout: 15000 });
    await panel(page).getByRole('button', { name: 'Back up and download' }).click();
    await received;
    await expect(panel(page).getByRole('button', { name: 'Back up and download' })).toBeEnabled();
  } finally { release(); }
});

test('stalled trigger acknowledgement is bounded and never claims a saved file', async ({ page }) => {
  await page.goto('/en/library/manage');
  await expect(panel(page).getByRole('button', { name: 'Download again' })).toBeEnabled();
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/maintenance/backups/*/download-triggered', async route => {
    await held;
    await route.abort('failed').catch(() => {});
  });
  try {
    const received = page.waitForEvent('download');
    await panel(page).getByRole('button', { name: 'Download again' }).click();
    await received;
    await expect(panel(page).getByText('Browser download triggered, but its status could not be recorded.', { exact: false })).toBeVisible({ timeout: 20000 });
    await expect(panel(page).getByRole('button', { name: 'Download again' })).toBeEnabled();
    await expect(panel(page).getByText('Generation and download-trigger status do not verify saving to your disk.', { exact: false })).toBeVisible();
  } finally { release(); }
});
