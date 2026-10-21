import assert from 'node:assert/strict';
import test from 'node:test';
import { createBaseUrlAutosave } from './settings-autosave.ts';
import { createAutosaveSessionRegistry } from './settings-autosave-session.ts';

function harness() {
  const registry = createAutosaveSessionRegistry(), writes = []; let made = 0;
  const options = () => { made += 1; return { initial: { base_url: 'https://initial.test' }, value: result => result.base_url, create: createBaseUrlAutosave,
    write: value => new Promise((resolve, reject) => writes.push({ value, resolve: () => resolve({ base_url: value }), reject })),
  }; };
  return { get: () => registry.get(options), fresh: () => registry.get(options, false), writes, made: () => made };
}

test('remount shares the pending flight and latest revision supersedes the old queued completion', async () => {
  const h = harness(), old = h.get(), leave = old.subscribe(() => {});
  old.edit('https://a.test'); const done = old.commit(); old.edit('https://c.test'); old.commit(); leave();
  const current = h.get(), detach = current.subscribe(() => {});
  assert.equal(current, old); assert.equal(h.made(), 1); assert.equal(current.getSnapshot().saving, true);
  current.edit('https://b.test'); current.commit(); assert.equal(h.writes.length, 1);
  h.writes[0].resolve(); await Promise.resolve(); await Promise.resolve();
  assert.deepEqual(h.writes.map(write => write.value), ['https://a.test', 'https://b.test']);
  h.writes[1].resolve(); await done;
  assert.equal(current.getSnapshot().draft, null); assert.equal(current.getSnapshot().result.base_url, 'https://b.test'); detach();
});

test('a failed old flight retains the newly mounted input and retries the same shared session', async () => {
  const h = harness(), old = h.get(), leave = old.subscribe(() => {});
  old.edit('https://a.test'); const done = old.commit(); leave();
  const current = h.get(), detach = current.subscribe(() => {});
  current.edit('https://new.test'); current.commit(); h.writes[0].reject(Error('503')); await done;
  assert.equal(current.getSnapshot().draft, 'https://new.test'); assert.equal(current.getSnapshot().notice, 'baseUrlSaveFailed');
  const retry = current.commit(); h.writes[1].resolve(); await retry;
  assert.equal(current.getSnapshot().result.base_url, 'https://new.test'); detach();
});

test('same-turn reattachment retains drafts; an idle abandoned draft is discarded after detachment', async () => {
  const h = harness(), session = h.get(), detach = session.subscribe(() => {});
  session.edit('https://draft.test'); detach(); const again = session.subscribe(() => {}); await Promise.resolve();
  assert.equal(session.getSnapshot().draft, 'https://draft.test'); again(); await Promise.resolve();
  assert.equal(h.get().getSnapshot().draft, null); assert.equal(h.writes.length, 0);
});

test('SSR sessions are not retained across requests', () => {
  const h = harness(); assert.notEqual(h.fresh(), h.fresh()); assert.equal(h.made(), 2);
});
