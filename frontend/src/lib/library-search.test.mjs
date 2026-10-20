import assert from 'node:assert/strict';
import test from 'node:test';
import { librarySearchHref, normalizeLibrarySearch } from './library-search.ts';
import { normalizeFilmPage } from './film-pagination.ts';

test('global search normalizes whitespace, duplicate values, empty and long input', () => {
  assert.equal(normalizeLibrarySearch(['  电影 & Orbit  ', 'ignored']), '电影 & Orbit');
  assert.equal(librarySearchHref('   '), '/library');
  assert.equal(librarySearchHref(undefined), '/library');
  assert.equal(new URL(librarySearchHref('x'.repeat(220)), 'https://local.test').searchParams.get('q').length, 200);
});

test('fresh search has only a safely encoded keyword and legacy pagination stays bounded', () => {
  const query = '电影 & ?page=9# / <script>';
  const url = new URL(librarySearchHref(query), 'https://local.test');
  assert.equal(url.pathname, '/library');
  assert.deepEqual([...url.searchParams], [['q', query]]);
  assert.equal(url.hash, '');
  assert.equal(librarySearchHref('Orbit', normalizeFilmPage('2')), '/library?q=Orbit&page=2');
  assert.equal(librarySearchHref('Orbit', normalizeFilmPage('-1')), '/library?q=Orbit');
  assert.equal(librarySearchHref('', normalizeFilmPage('9')), '/library');
});
