import test from 'node:test';
import assert from 'node:assert/strict';
import { metadataChanges, metadataDraft, metadataModes, metadataRequestKey, isMetadataReadCache } from './film-metadata.ts';
const view = { film_id: 'film', revision: 'v1', fields: Object.fromEntries(
  Object.entries({ title: 'Source title', original_title: null, year: 1999, overview: 'Source plot' })
    .map(([key, value]) => [key, { value, manual: false, automatic_value: value }])) };
test('request keys work without secure-context randomUUID and stay within the API contract', () => {
  const key = metadataRequestKey({ getRandomValues: bytes => bytes.fill(255) });
  assert.match(key, /^[a-f0-9]{32}$/);
  assert.equal(key, 'ff'.repeat(16));
});
test('metadata refresh covers graph, missing and explore reads without changing write caches', () => {
  for (const key of ['/api/films/a/graph', '/api/films/b/metadata', '/api/library/missing', '/api/explore', '/api/explore/concept/a']) assert.equal(isMetadataReadCache(key), true);
  for (const key of ['/api/films/a/scrape', '/api/operations/a', '/api/settings']) assert.equal(isMetadataReadCache(key), false);
});
test('unchanged fields are omitted; only typed/manual fields are protected', () => {
  const draft = metadataDraft(view), modes = metadataModes(view);
  assert.deepEqual(metadataChanges(view, draft, modes), {});
  draft.title = '  Corrected  '; modes.title = true;
  assert.deepEqual(metadataChanges(view, draft, modes), { title: { action: 'set', value: 'Corrected' } });
});
test('blank year is an explicit protected null, reset is a different command', () => {
  const draft = metadataDraft(view), modes = metadataModes(view);
  draft.year = ''; modes.year = true;
  assert.deepEqual(metadataChanges(view, draft, modes), { year: { action: 'set', value: null } });
  const edited = structuredClone(view); edited.fields.year.value = null; edited.fields.year.manual = true;
  assert.deepEqual(metadataChanges(edited, metadataDraft(edited), metadataModes(edited)), {});
  const reset = metadataModes(edited); reset.year = false;
  assert.deepEqual(metadataChanges(edited, metadataDraft(edited), reset), { year: { action: 'reset' } });
});
test('manual blank text remains distinct from automatic; same current automatic value can be protected', () => {
  const modes = metadataModes(view); modes.original_title = true; modes.title = true;
  assert.deepEqual(metadataChanges(view, metadataDraft(view), modes), {
    title: { action: 'set', value: 'Source title' }, original_title: { action: 'set', value: null },
  });
});
test('validation rejects noncanonical years, whitespace title and length overflow', () => {
  for (const value of ['18', '1869', '2101', '1999.5', '2e03', '-1', 'abcd']) {
    assert.throws(() => metadataChanges(view, { ...metadataDraft(view), year: value }, { ...metadataModes(view), year: true }), /year/);
  }
  for (const value of ['   ', 'a'.repeat(301)]) assert.throws(() => metadataChanges(view,
    { ...metadataDraft(view), title: value }, { ...metadataModes(view), title: true }), /title/);
});
