import assert from 'node:assert/strict';
import test from 'node:test';
import { createBaseUrlAutosave, createMediaRootsAutosave, createTmdbKeyAutosave, restoreBlankRootEdits, validateBaseUrl, validateRootDraft } from './settings-autosave.ts';

const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; };
function harness() {
  let saved = ['/media/a'], state;
  const writes = [];
  const control = createMediaRootsAutosave({ initial: saved, changed: value => { state = value; }, write: paths => {
    const pending = deferred(); writes.push({ paths, ...pending }); return pending.promise.then(value => { saved = value; return value; });
  } });
  return { control, writes, state: () => state, saved: () => saved };
}

test('completion accepts host absolute paths and rejects empty/unfinished paths without requesting a save', async () => {
  for (const value of ['/media', 'D:\\Movies', '\\\\nas\\films', '~/Movies']) assert.equal(validateRootDraft([value]).error, null);
  for (const value of ['', 'C:', '\\\\nas', 'relative', '~']) assert.ok(validateRootDraft([value]).error);
  assert.deepEqual(validateRootDraft([]), { paths: [], error: null });
  const h = harness(); h.control.edit(['/media/a', '']); await h.control.commit();
  assert.equal(h.writes.length, 0); assert.equal(h.state().notice, 'incomplete');
  h.control.edit(['/media/a', 'relative']); await h.control.commit();
  assert.equal(h.writes.length, 0); assert.equal(h.state().notice, 'absolute');
});

test('typing is draft-only; completion trims and server-normalized success wins only its own revision', async () => {
  const h = harness(); h.control.edit([' /media/b ', '/media/b']); assert.equal(h.writes.length, 0);
  const done = h.control.commit(); h.control.commit(); assert.equal(h.writes.length, 1);
  assert.deepEqual(h.writes[0].paths, ['/media/b', '/media/b']); assert.equal(h.state().saving, true);
  h.writes[0].resolve(['/media/b']); await done;
  assert.deepEqual(h.state(), { draft: null, saving: false, notice: 'saved' });
});

test('one request runs at a time and completed newer edits coalesce into the latest request', async () => {
  const h = harness(); h.control.edit(['/media/b']); const done = h.control.commit();
  h.control.edit(['/media/c']); h.control.commit(); h.control.edit(['/media/d']); h.control.commit();
  assert.equal(h.writes.length, 1); h.writes[0].resolve(['/media/b']); await Promise.resolve(); await Promise.resolve();
  assert.equal(h.writes.length, 2); assert.deepEqual(h.writes[1].paths, ['/media/d']); assert.deepEqual(h.state().draft, ['/media/d']);
  h.writes[1].resolve(['/media/d']); await done; assert.equal(h.state().draft, null); assert.deepEqual(h.saved(), ['/media/d']);
});

test('further unfinished typing invalidates an older queued completion and survives old responses', async () => {
  const h = harness(); h.control.edit(['/media/b']); const done = h.control.commit();
  h.control.edit(['/media/c']); h.control.commit(); h.control.edit(['/media/d', '']);
  h.writes[0].resolve(['/media/b']); await done;
  assert.equal(h.writes.length, 1); assert.deepEqual(h.state().draft, ['/media/d', '']); assert.equal(h.state().saving, false);
  assert.notEqual(h.state().notice, 'saved');
});

test('failed writes retain latest input, discard stale queues and allow explicit retry', async () => {
  const h = harness(); h.control.edit(['/media/b']); const done = h.control.commit();
  h.control.edit(['/media/c']); h.control.commit(); h.writes[0].reject(new Error('overlap')); await done;
  assert.deepEqual(h.state(), { draft: ['/media/c'], saving: false, notice: 'saveFailed' }); assert.equal(h.writes.length, 1);
  const retry = h.control.commit(); h.writes[1].resolve(['/media/c']); await retry;
  assert.equal(h.state().draft, null); assert.deepEqual(h.saved(), ['/media/c']);
});

test('removing all roots saves an empty list and Discard cannot contradict an in-flight write', async () => {
  const h = harness(); h.control.edit([]); const done = h.control.commit(); h.control.discard();
  assert.deepEqual(h.state().draft, []); assert.equal(h.state().saving, true);
  h.writes[0].resolve([]); await done; h.control.edit(['/media/new']); h.control.discard();
  assert.deepEqual(h.state(), { draft: null, saving: false, notice: null }); assert.deepEqual(h.saved(), []);
});

test('returning to the confirmed list finishes a draft without writing it again', async () => {
  const h = harness(); h.control.edit(['/media/b']); h.control.edit(['/media/a']); await h.control.commit();
  assert.equal(h.writes.length, 0); assert.equal(h.state().draft, null);
});

test('a refreshed saved configuration never replaces an active draft', async () => {
  const h = harness(); h.control.edit(['/media/user']); h.control.syncSaved(['/media/server']);
  assert.deepEqual(h.state().draft, ['/media/user']); h.control.discard();
  h.control.edit(['/media/server']); await h.control.commit(); assert.equal(h.writes.length, 0);
});

test('base URLs require completed HTTP(S) URLs and preserve the original trimmed value', () => {
  for (const value of ['', 'https://', 'ftp://example.test', 'relative']) assert.equal(validateBaseUrl(value).error, 'invalidBaseUrl');
  assert.deepEqual(validateBaseUrl(' https://example.test/api/v1 '), { value: 'https://example.test/api/v1', error: null });
});

test('blank root edits restore saved entries and do not resurrect a superseded pending path', async () => {
  const h = harness();
  assert.deepEqual(restoreBlankRootEdits(['  ', ''], h.control.baseline()), ['/media/a']);
  h.control.edit(['/media/b']); const done = h.control.commit();
  h.control.edit(['/media/c']); h.control.commit();
  const restored = restoreBlankRootEdits([''], h.control.baseline());
  assert.deepEqual(restored, ['/media/c']); h.control.edit(restored); h.control.commit();
  h.writes[0].resolve(['/media/b']); await Promise.resolve(); await Promise.resolve();
  assert.deepEqual(h.writes[1].paths, ['/media/c']);
  h.writes[1].resolve(['/media/c']); await done;
  assert.deepEqual(h.saved(), ['/media/c']);
});

test('TMDB keys save only completed drafts, retain failures, and explicitly clear with a completed blank', async () => {
  let state; const writes = [];
  const control = createTmdbKeyAutosave({ initial: null, changed: value => { state = value; }, write: value => {
    const pending = deferred(); writes.push({ value, ...pending }); return pending.promise;
  } });
  await control.commit(); assert.equal(writes.length, 0);
  control.edit(' synthetic-first '); assert.equal(writes.length, 0); const done = control.commit();
  control.edit('synthetic-latest'); control.commit(); writes[0].reject(Error('private provider detail')); await done;
  assert.deepEqual(state, { draft: 'synthetic-latest', saving: false, notice: 'tmdbSaveFailed' });
  const retry = control.commit(); assert.equal(writes[1].value, 'synthetic-latest'); writes[1].resolve('synthetic-latest'); await retry;
  control.edit(' '); const clear = control.commit(); assert.equal(writes[2].value, ''); writes[2].resolve(''); await clear;
  assert.equal(state.draft, null); control.edit('bad\nkey'); await control.commit(); assert.equal(writes.length, 3); assert.equal(state.notice, 'invalidTmdbKey');
});

test('blank restoration after a failed removal keeps the remaining root identity instead of an old index', async () => {
  let state;
  const control = createMediaRootsAutosave({ initial: ['/media/a', '/media/b'], changed: value => { state = value; }, write: async () => { throw Error('503'); } });
  control.edit(['/media/b']); await control.commit(); assert.equal(state.notice, 'saveFailed');
  control.edit(['']); assert.deepEqual(restoreBlankRootEdits([''], control.baseline()), ['/media/b']);
});

test('URL saves serialize, retain newer typing and retry without modifying another setting', async () => {
  let state; const writes = [];
  const control = createBaseUrlAutosave({ initial: 'https://initial.test/v1', changed: value => { state = value; }, write: value => {
    const pending = deferred(); writes.push({ value, ...pending }); return pending.promise;
  } });
  control.edit('https://'); await control.commit(); assert.equal(writes.length, 0); assert.equal(state.notice, 'invalidBaseUrl');
  control.edit('https://first.test/v1'); const first = control.commit();
  control.edit('https://latest.test/v1'); control.commit(); assert.equal(writes.length, 1);
  writes[0].reject(new Error('503')); await first;
  assert.deepEqual(state, { draft: 'https://latest.test/v1', saving: false, notice: 'baseUrlSaveFailed' });
  const retry = control.commit(); assert.equal(writes[1].value, 'https://latest.test/v1');
  control.edit('https://unfinished'); writes[1].resolve('https://latest.test/v1'); await retry;
  assert.equal(state.draft, 'https://unfinished'); assert.equal(state.notice, null); assert.equal(writes.length, 2);
});
