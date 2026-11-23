import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { copyFile, mkdtemp, utimes, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { promisify } from 'node:util';
import { repeated, timed } from './metrics.mjs';

export async function measureMaintenance({
  api,
  control,
  until,
  workflow,
  root,
  media,
  film,
  metrics,
  python,
  lastTier,
}) {
  await control('performance_analysis', { film_id: film.id });
  let originalRun;
  for (const name of ['generate', 'reuse']) {
    await timed(metrics, 'job.analysis-' + name + '-fixture', async () => {
      const ack = await api('/films/' + film.id + '/analysis-runs', 'POST');
      await workflow(ack.workflow_id);
    });
    const analysis = await api('/films/' + film.id + '/analysis');
    assert.equal(analysis.status, 'succeeded');
    assert.equal(analysis.summary, 'Synthetic performance sample.');
    if (name === 'generate') originalRun = analysis.run.id;
    else assert.equal(analysis.run.id, originalRun);
  }
  const question = 'films about a family reunion';
  const fixture = await control('semantic_evaluation', { enabled: true, queries: [question] });
  assert.equal(fixture.indexed_films, 12);
  try {
    const result = await timed(metrics, 'search.semantic-fixture', () =>
      api('/explore/search/interpret', 'POST', { question, locale: 'en', allow_ai: true }),
    );
    assert.ok(result.snapshot && result.plan);
    const replay = { question, plan: result.plan, semantic_snapshot: result.snapshot };
    await repeated(metrics, 'search.semantic-replay', async () => {
      const restored = await api('/explore/search/query', 'POST', replay);
      assert.equal(restored.snapshot, result.snapshot);
    });
    assert.deepEqual((await control('semantic_stats')).calls, ['decision', 'embedding', 'rerank']);
  } finally {
    await control('semantic_evaluation', { enabled: false });
  }
  const events = (id) => api('/activity/events?aggregate_id=' + id + '&limit=100');
  const edition = film.primary_item.id;
  for (let i = 0; i < 5; i++) {
    await timed(metrics, 'maintenance.ignore-edition', () =>
      api('/library/items/' + edition + '/ignore', 'POST'),
    );
    const event = (await events(edition)).find((event) => event.type === 'LibraryItemIgnored');
    const preview = '/operations/' + event.operation_snapshot_id;
    const snapshot = await timed(metrics, 'maintenance.restore-preview', () => api(preview + '/preview'));
    assert.ok(snapshot.current_matches_after && snapshot.confirmation_token);
    await timed(metrics, 'maintenance.restore', () =>
      api(preview + '/restore', 'POST', { confirmation_token: snapshot.confirmation_token }),
    );
    assert.equal((await api(preview + '/preview')).status, 'restored');
  }
  await repeated(metrics, 'metadata.candidates-fixture', async () => {
    const results = await api('/films/' + film.id + '/scrape/candidates');
    assert.ok(results.length);
  });
  const confirmed = await timed(metrics, 'metadata.confirm-fixture', () =>
    api('/films/' + film.id + '/scrape/confirm?tmdb_id=' + film.identities.tmdb, 'POST', {
      write_nfo: false,
      download_artwork: false,
    }),
  );
  assert.equal(confirmed.film.id, film.id);

  const source = 'Performance root video.mp4';
  await copyFile(path.join(media, 'film-0001', 'film.mp4'), path.join(media, source));
  await utimes(path.join(media, source), 1000000000, 1000000000);
  const plan = { source_path: source, tmdb_id: 900077, rename_style: 'preserve_stem' };
  let preview;
  await repeated(metrics, 'organization.preview-fixture', async () => {
    preview = await api('/library/organization/preview', 'POST', plan);
    assert.ok(preview.can_confirm && preview.confirmation_token);
  });
  await timed(metrics, 'job.organize-fixture', async () => {
    const ack = await api('/library/organization/confirm', 'POST', {
      ...plan,
      confirmation_token: preview.confirmation_token,
    });
    await workflow(ack.workflow_id);
  });

  // The canary fixture allows the existing offline restore and boot probe to verify the archive.
  const backupFilm = lastTier ? await control('backup_fixture') : null;
  let archive;
  for (let i = 0; i < 3; i++) {
    const id = randomUUID().replaceAll('-', '');
    const receipt = await timed(metrics, 'job.backup', async () => {
      await api('/maintenance/backups', 'POST', { request_id: id });
      return until(
        () => api('/maintenance/backups/' + id),
        (r) => r.status !== 'generating',
      );
    });
    assert.equal(receipt.status, 'succeeded');
    archive = await timed(metrics, 'backup.download', () => api('/maintenance/backups/' + id + '/download'));
    assert.equal(archive.length, receipt.size_bytes);
  }
  if (backupFilm) {
    const restoreRoot = await mkdtemp(path.join(root, '5x49-e2e-restore-'));
    await writeFile(path.join(restoreRoot, '.owned'), '5X49 E2E');
    const zip = path.join(restoreRoot, 'snapshot.zip');
    await writeFile(zip, archive);
    await timed(metrics, 'backup.restore-verify-boot', async () => {
      const { stdout } = await promisify(execFile)(
        python,
        ['-X', 'utf8', path.resolve('e2e/backup_restore.py'), zip, backupFilm.film_id],
        { env: { ...process.env, E2E_ROOT: restoreRoot }, timeout: 180000, cwd: restoreRoot },
      );
      assert.equal(JSON.parse(stdout.trim().split(/\r?\n/).at(-1)).actual_application_boot, true);
    });
  }

  // These workflows exercise queue bookkeeping without racing the worker.
  const tasks = await control('tasks');
  try {
    for (const job of tasks) {
      const cancelled = await timed(metrics, 'workflow.cancel', () =>
        api('/workflows/' + job.id + '/cancel', 'POST'),
      );
      assert.equal(cancelled.status, 'cancelled');
      const retried = await timed(metrics, 'workflow.retry', () =>
        api('/workflows/' + job.id + '/retry', 'POST'),
      );
      await api('/workflows/' + retried.workflow_id + '/cancel', 'POST');
    }
  } finally {
    await control('resume_tasks');
  }

  // The two-file decode and identity-decision fixtures need a fresh catalogue.
  const cleared = await timed(metrics, 'maintenance.clear-data', () => api('/library/data', 'DELETE'));
  assert.ok(cleared.deleted.films > 0);
  if (!lastTier) return;
  const review = await control('identity_fixtures');
  await api('/settings/media-dirs', 'PUT', { media_dirs: [root] });
  const route = '/library/identity-reviews/' + review.review_id;
  let decision;
  await repeated(metrics, 'identity.preview', async () => {
    decision = await api(route + '/preview', 'POST', { action: 'keep_separate' });
    assert.ok(decision.confirmation_token);
  });
  const saved = await timed(metrics, 'identity.keep-separate', () =>
    api(route + '/confirm', 'POST', {
      action: 'keep_separate',
      confirmation_token: decision.confirmation_token,
      idempotency_key: randomUUID(),
    }),
  );
  assert.equal(saved.action, 'keep_separate');
  await api('/library/data', 'DELETE');
  await control('health_fixture');
  const health = '/maintenance/video-health';
  await api(health + '/config', 'PUT', { start_minute: 0, end_minute: 0, daily_budget_minutes: 5 });
  await control('health_allow');
  await timed(metrics, 'video.queue', () => api(health + '/queue', 'POST'));
  await timed(metrics, 'video.resume-to-results', async () => {
    await api(health + '/config', 'PUT', { enabled: true, paused: false });
    await until(
      () => api(health),
      (s) => s.counts.abnormal > 0 && s.counts.passed > 0,
      120000,
    );
  });
  await api(health + '/config', 'PUT', { paused: true });
  const files = await api(health + '/files?status=abnormal');
  assert.ok(files.total > 0);
  // Exercise the result reader as well as the actual FFmpeg worker.
  await repeated(metrics, 'video.abnormal-list', () => api(health + '/files?status=abnormal'));
}
