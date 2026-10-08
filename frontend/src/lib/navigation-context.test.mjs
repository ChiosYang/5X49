import test from 'node:test';
import assert from 'node:assert/strict';
import { safeReturnHref, parseReturnContext } from './navigation-context.ts';
test('return destinations preserve local list queries and reject external/detail paths', () => {
  for (const href of ['/library?filter=unwatched&sort=added', '/en/ask', '/zh/search?q=film', '/diary?film=x']) assert.equal(safeReturnHref(href), href);
  for (const href of ['https://evil.test', '//evil.test', '/library/film_x', '/library\\evil', '/settings', '/%2f%2fevil', '/library\n']) assert.equal(safeReturnHref(href), null);
});
test('return context rejects stale or malformed state, preserves focus and scroll only', () => {
  const context = { href:'/ask',filmId:`film_${'a'.repeat(32)}`,scrollY:420,savedAt:1000 };
  assert.deepEqual(parseReturnContext(JSON.stringify(context), 2000), context);
  assert.equal(parseReturnContext(JSON.stringify(context), 2000000),null);
  assert.equal(parseReturnContext(JSON.stringify({...context,scrollY:-1}),2000),null);
  assert.equal(parseReturnContext('oops'),null);
  const focusId = `viewing-link-view_${'b'.repeat(32)}`;
  assert.deepEqual(parseReturnContext(JSON.stringify({...context,focusId}),2000), {...context,focusId});
  assert.deepEqual(parseReturnContext(JSON.stringify({...context,focusId:'unrelated-control'}),2000), context);
});
