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
test('Explore returns cover known local list routes and preserve their queries', () => {
  const person = `person_${'b'.repeat(32)}`;
  for (const prefix of ['', '/en', '/zh']) for (const route of [
    '/explore/filter?person='+person+'&person_match=all&view=unwatched&sort=year&offset=40',
    '/explore/search?q=Shelf&page=2', '/explore/collections?category=country&offset=24',
    '/explore/collections/director/'+person+'?view=unwatched&sort=year&dir=asc&offset=40',
    '/explore/collections/person/'+person, '/explore/collections/country/JP', '/explore/collections/decade/1980',
  ]) assert.equal(safeReturnHref(prefix+route), prefix+route);
  for (const value of ['https://evil.test/explore/filter', '//evil.test/explore/filter', '///evil.test/explore/filter',
    '/explore/other', '/explore/filter/country/JP', '/explore/collections/series/unknown',
    '/explore/collections/person/invalid', '/explore/collections/country/Japan', '/explore/collections/decade/1995',
    '/explore/filter/../../library/film_x', '/explore/collections/country/JP/extra',
    '/explore/collections/person/%2f%2fevil.test', '/en/explore/search\t?x=1', '/explore/collections\\evil',
  ]) assert.equal(safeReturnHref(value), null, value);
});

test('video inspection return context allows only its scoped local settings category', () => {
  const href = '/en/settings?section=video-checks&health_state=all&health_offset=20&health_file=health_abc';
  assert.equal(safeReturnHref(href), href);
  assert.equal(safeReturnHref('/settings?section=cleanup'), null);
  assert.equal(safeReturnHref('//evil.test/settings?section=video-checks'), null);
  assert.equal(safeReturnHref('/settings/other?section=video-checks'), null);
});
