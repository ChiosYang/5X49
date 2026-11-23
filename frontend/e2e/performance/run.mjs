import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createHash, randomUUID } from 'node:crypto';
import { mkdir, readFile, writeFile, realpath, stat } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { setTimeout as sleep } from 'node:timers/promises';
import { chromium } from 'playwright';
import { measureBrowser } from './browser.mjs';
import { record, repeated, summarize, timed } from './metrics.mjs';
import { measureMaintenance } from './maintenance.mjs';

const [size, webPid, backendReadyMs, frontendReadyMs] = process.argv.slice(2).map(Number);
const root = await realpath(process.env.E2E_ROOT);
assert.ok(path.basename(root).startsWith('5x49-e2e-'));
assert.equal(await readFile(path.join(root, '.owned'), 'utf8'), '5X49 E2E');
const backend = process.env.E2E_BACKEND,
  origin = process.env.E2E_BASE_URL;
for (const url of [origin, backend]) assert.match(url, /^http:\/\/127\.0\.0\.1:\d+$/);
const python = path.resolve(
  '../backend/.venv',
  process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python',
);
const started = new Date();
const output = path.resolve('e2e-artifacts', 'performance-' + started.toISOString().replace(/[:.]/g, '-'));
await mkdir(output, { recursive: true });

async function api(route, method = 'GET', body, headers = {}) {
  const response = await fetch(backend + route, {
    method,
    headers: { 'Content-Type': 'application/json', ...headers },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(120000),
    redirect: 'error',
  });
  if (!response.ok) {
    const error = new Error(method + ' ' + route.split('?')[0] + ' HTTP ' + response.status);
    error.status = response.status;
    throw error;
  }
  if (response.headers.get('content-type')?.includes('application/zip'))
    return Buffer.from(await response.arrayBuffer());
  return response.json();
}
const control = (action, extra = {}) =>
  api('/__e2e/control', 'POST', { action, ...extra }, { 'x-e2e-token': process.env.E2E_TOKEN });
const { pid: backendPid } = await control('performance_process');
assert.ok(Number.isInteger(backendPid) && backendPid > 0);
const settings = await api('/settings/media-dir');
assert.equal(await realpath(settings.media_dir), await realpath(path.join(root, 'empty')));

async function until(read, complete, timeout = 120000) {
  const deadline = performance.now() + timeout;
  while (performance.now() < deadline) {
    const value = await read();
    if (complete(value)) return value;
    await sleep(250);
  }
  throw Error('Completion deadline exceeded');
}
async function waitForWorkflow(id, pollErrors) {
  assert.ok(id);
  return until(
    async () => {
      try {
        return await api('/workflows/' + id);
      } catch (error) {
        // A locked scan can temporarily make its status unreadable. Record each failed read,
        // then keep observing the original job without enqueueing another one.
        if (!pollErrors || ![500, 503].includes(error.status)) throw error;
        pollErrors[error.status] = (pollErrors[error.status] ?? 0) + 1;
        return null;
      }
    },
    (job) => job && ['succeeded', 'failed', 'cancelled'].includes(job.status),
    1800000,
  );
}
async function workflow(id) {
  const done = await waitForWorkflow(id);
  assert.equal(done.status, 'succeeded', [done.type, done.current_step, done.error_code].join(' '));
  return done;
}
function serviceResources() {
  const code =
    'import psutil,sys,json; ps=[psutil.Process(int(pid)) for pid in sys.argv[1:]]; print(json.dumps([dict(rssMiB=round(p.memory_info().rss/1048576,1),cpuSeconds=round(sum(p.cpu_times()[:2]),2)) for p in ps]))';
  const [fastapi, next] = JSON.parse(
    execFileSync(python, ['-c', code, String(backendPid), String(webPid)], { encoding: 'utf8' }),
  );
  return { fastapi, next };
}
const hash = createHash('sha256');
for (const filename of [
  'e2e/run.mjs',
  'e2e/backend.py',
  'e2e/semantic_fixture.py',
  'e2e/backup_restore.py',
  '../backend/scripts/generate_test_data.py',
  'e2e/performance/run.mjs',
  'e2e/performance/maintenance.mjs',
  'e2e/performance/browser.mjs',
  'e2e/performance/metrics.mjs',
]) {
  hash.update(filename + '\n' + (await readFile(filename, 'utf8')).replaceAll('\r\n', '\n'));
}
// An exported Git archive has no .git directory. Its creator records the exported SHA beside frontend/.
let revision;
try {
  revision = (await readFile('../.performance-revision', 'utf8')).trim();
} catch (error) {
  if (error.code !== 'ENOENT') throw error;
  revision = execFileSync('git', ['rev-parse', 'HEAD'], {encoding:'utf8'}).trim();
}
assert.match(revision, /^[0-9a-f]{40}$/);
const report = {
  schema: 1,
  started: started.toISOString(),
  commit: revision,
  workloadSha256: hash.digest('hex'),
  platform: [os.platform(), os.release(), os.arch()].join(' '),
  cpu: os.cpus()[0].model,
  logicalCpus: os.cpus().length,
  memoryGiB: Math.round(os.totalmem() / 2 ** 30),
  node: process.version,
  startupMs: { backendReadyMs, frontendReadyMs },
  next: JSON.parse(await readFile('node_modules/next/package.json', 'utf8')).version,
  playwright: JSON.parse(await readFile('node_modules/playwright/package.json', 'utf8')).version,
  ffmpeg: execFileSync('ffmpeg', ['-version'], { encoding: 'utf8' }).split(/\r?\n/)[0],
  pythonAndSqlite: execFileSync(
    python,
    ['-c', 'import platform,sqlite3;print(platform.python_version(),sqlite3.sqlite_version)'],
    { encoding: 'utf8' },
  ).trim(),
  fixture: { seed: 549, videoMode: 'valid', profile: 'normal' },
  tiers: [],
  complete: false,
};
const checkpoint = () => writeFile(path.join(output, 'report.json'), JSON.stringify(report, null, 2) + '\n');
console.log('Performance report:', output);

async function core(tier, film, metrics) {
  const base = '/films/' + film.id;
  const page = '/library/films/page?limit=40';
  const keyword = page + '&q=' + encodeURIComponent(film.title);
  const renderFilm = '/library/films/' + film.id;
  const catalogue = [];
  for (let offset = 0; offset < tier.films; offset += 100) {
    catalogue.push(...(await api('/library/films/page?limit=100&offset=' + offset)).items);
  }
  assert.equal(new Set(catalogue.map((row) => row.id)).size, tier.films);
  catalogue.sort((a, b) => Number(a.identities.tmdb) - Number(b.identities.tmdb));
  for (let index = 0; index < catalogue.length; index += 5) {
    const subject = '/films/' + catalogue[index].id;
    const rating = 1 + ((index / 5) % 5);
    const watched_at = '2026-01-' + String(1 + ((index / 5) % 28)).padStart(2, '0');
    const watch = await api(subject + '/viewings', 'POST', {
      watched_at,
      rating,
      idempotency_key: randomUUID(),
    });
    assert.ok(watch.id);
    await api(subject + '/profile-state', 'PUT', { favorite: index % 10 === 0, rating });
  }
  await api(base + '/profile-state', 'PUT', { favorite: true, rating: 4 });
  tier.viewings = (await api('/profile/cinema-dna')).totals.viewing_records;
  assert.equal(tier.viewings, Math.ceil(tier.films / 5));
  tier.sqliteFileBytes = (await stat(process.env.SQLITE_DB_PATH)).size;
  const catalog = await api('/explore/catalog?limit=24');
  const collection = catalog.items[0];
  assert.ok(collection?.key);
  const filter = page + '&favorite=true&rating_min=3&sort=duration&direction=desc';
  const paths = [
    ['health', '/health'],
    ['library', page],
    ['library-last-page', page + '&offset=' + Math.floor((tier.films - 1) / 40) * 40],
    ['keyword', keyword],
    ['filter-and-sort', filter],
    ['film', renderFilm],
    ['graph', base + '/graph'],
    ['metadata', base + '/metadata'],
    ['analysis-state', base + '/analysis'],
    ['analysis-review', base + '/analysis-review'],
    ['catalog', '/explore/catalog?limit=24'],
    ['collection', '/explore/collections/' + collection.kind + '/' + encodeURIComponent(collection.key)],
    ['people-suggest', '/explore/facets/person?q=Director&limit=12'],
    ['diary', '/profile/viewings?limit=40'],
    ['cinema-dna', '/profile/cinema-dna'],
    ['activity', '/activity/events?limit=100'],
    ['workflows', '/workflows?limit=8&include_active=true'],
    ['media-roots', '/settings/media-dirs'],
    ['sync-status', '/library/sync/status'],
    ['video-health', '/maintenance/video-health'],
    ['metadata-queue', page + '&metadata_status=pending'],
    ['identity-queue', '/library/identity-reviews'],
    ['offline-items', '/library/missing'],
    ['organization-queue', '/library/organization/candidates'],
    ['score-refresh-status', '/library/external-scores/status'],
    ['backup-status', '/maintenance/backups'],
    ['diagnostics', '/diagnostics'],
    ['connections-config', '/settings/model'],
  ];
  assert.equal((await api(page)).library_total, tier.films);
  assert.ok((await api(keyword)).items.length);
  const filtered = await api(filter);
  assert.ok(filtered.items.length > 0);
  assert.ok(filtered.items.every((item) => item.profile_state.favorite && item.profile_state.rating >= 3));
  assert.ok((await api(base + '/graph')).edges.length);
  for (const [name, route] of paths) await repeated(metrics, 'api.' + name, () => api(route));

  for (const [name, endpoint, question, status] of [
    ['rule', 'interpret', 'Japanese films', 'ready'],
    ['plot', 'plot', 'films about a local fixture', 'plot'],
  ]) {
    await repeated(metrics, 'api.search-' + name, async () => {
      const payload =
        name === 'plot' ? { question, locale: 'en' } : { question, locale: 'en', allow_ai: false };
      const result = await api('/explore/search/' + endpoint, 'POST', payload);
      assert.equal(result.status, status);
      if (name === 'plot') assert.ok(result.plot_matches.length);
    });
  }

  const mixed = [page, keyword, renderFilm, base + '/graph'];
  tier.load = [];
  for (const clients of [1, 8]) {
    // Eight warm-up requests, then 80 closed-loop requests, same mix at both levels.
    for (let i = 0; i < 8; i++) await api(mixed[i % mixed.length]);
    let next = 0;
    const start = performance.now();
    await Promise.all(
      Array.from({ length: clients }, async () => {
        while (next < 80) {
          const route = mixed[next++ % mixed.length];
          await timed(metrics, 'load.' + clients + '-clients', () => api(route));
        }
      }),
    );
    tier.load.push({ clients, requests: 80, rps: Number((80000 / (performance.now() - start)).toFixed(2)) });
  }

  let favorite = true;
  let metadata = await api(base + '/metadata');
  for (let i = 0; i <= 20; i++) {
    const m = i === 0 ? {} : metrics;
    favorite = !favorite;
    const state = await timed(m, 'write.favorite', () => api(base + '/profile-state', 'PUT', { favorite }));
    assert.equal(state.favorite, favorite);
    const rating = (i % 5) + 1;
    const viewing = await timed(m, 'write.viewing-create', () =>
      api(base + '/viewings', 'POST', { watched_at: '2026-02-01', rating, idempotency_key: randomUUID() }),
    );
    assert.equal(viewing.rating, rating);
    const edited = await timed(m, 'write.viewing-edit', () =>
      api('/viewings/' + viewing.id, 'PATCH', {
        notes: 'Edited fixture',
        revision: viewing.revision,
        idempotency_key: randomUUID(),
      }),
    );
    assert.equal(edited.notes, 'Edited fixture');
    await timed(m, 'write.viewing-delete', () =>
      api('/viewings/' + viewing.id + '?revision=' + edited.revision, 'DELETE'),
    );
    const value = 'Fixture original ' + i;
    metadata = await timed(m, 'write.metadata', () =>
      api(base + '/metadata', 'PATCH', {
        revision: metadata.revision,
        idempotency_key: randomUUID(),
        changes: { original_title: { action: 'set', value } },
      }),
    );
    assert.equal(metadata.fields.original_title.value, value);
    const language = i % 2 ? 'en' : 'zh';
    await timed(m, 'write.language', () => api('/settings/language?language=' + language, 'PUT'));
    assert.equal((await api('/settings/language')).language, language);
  }
}

let browser;
try {
  browser = await chromium.launch({ executablePath: process.env.E2E_CHROMIUM_PATH || undefined });
  report.chromium = browser.version();
  for (const [name, films] of [
    ['normal', 12],
    ['scale', size],
  ]) {
    const tier = { films, metrics: {}, resources: {}, completedStages: [], scans: {} };
    report.tiers.push(tier);
    const metrics = {};
    async function savedStage(name) {
      tier.completedStages.push(name);
      tier.metrics = summarize(metrics);
      await checkpoint();
    }
    try {
      assert.equal((await api('/library/films/page')).library_total, 0);
      const media = await realpath(path.join(root, name, 'media'));
      await api('/settings/media-dirs', 'PUT', { media_dirs: [media] });
      for (const action of ['initial-scan', 'repeat-scan']) {
        console.log(films, action);
        const start = performance.now();
        const receipt = await timed(metrics, 'enqueue.' + action, () => api('/library/scan', 'POST'));
        const pollErrors = {};
        const done = await waitForWorkflow(receipt.workflow_id, pollErrors);
        const elapsed = performance.now() - start;
        const visible = (await api('/library/films/page?limit=1')).library_total;
        const scan = (await api('/library/sync/status')).sync;
        tier.scans[action] = {
          pollErrors,
          status: done.status,
          step: done.current_step,
          code: done.error_code,
          error: scan.last_error,
          elapsedMs: Math.round(elapsed),
          visibleFilms: visible,
        };
        if (done.status === 'succeeded') {
          assert.ok(scan.last_result.complete);
          record(metrics, 'job.' + action, elapsed);
        } else {
          console.log(films, action, tier.scans[action]);
          // Keep failed single-root scans visible; never count recovery as a successful scan.
          assert.ok(name === 'scale' && done.status === 'failed', 'Unexpected scan outcome');
          if (action === 'initial-scan') {
            assert.equal(visible, 0);
            const fixtureStart = performance.now();
            for (let offset = 0; offset < films; offset += 20) {
              const batch = await control('performance_import_batch', { offset });
              assert.equal(batch.created, Math.min(20, films - offset));
            }
            tier.fixtureLoad = {
              method: 'NFO observations in batches of 20',
              elapsedMs: Math.round(performance.now() - fixtureStart),
            };
          }
        }
        assert.equal((await api('/library/films/page')).library_total, films);
        await savedStage(action);
      }
      const film = (await api('/library/films/page?limit=1')).items[0];
      tier.resources.afterScan = serviceResources();
      console.log(films, 'API reads, writes and concurrent reads');
      await core(tier, film, metrics);
      tier.resources.afterApi = serviceResources();
      await savedStage('api');
      console.log(films, 'browser pages and interactions');
      await measureBrowser(browser, origin, film, metrics);
      tier.resources.afterBrowser = serviceResources();
      await savedStage('browser');
      console.log(films, 'maintenance');
      await measureMaintenance({
        api,
        control,
        until,
        workflow,
        root,
        media,
        film,
        metrics,
        python,
        lastTier: name === 'scale',
      });
      await savedStage('maintenance');
    } finally {
      tier.metrics = summarize(metrics);
      await checkpoint();
    }
  }
  report.complete = true;
} finally {
  await browser?.close();
  report.finished = new Date().toISOString();
  await checkpoint();
}
