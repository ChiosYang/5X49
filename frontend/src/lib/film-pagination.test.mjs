import assert from 'node:assert/strict';
import test from 'node:test';
import { normalizeFilmPage, filmPageHref } from './film-pagination.ts';

test('pagination keeps search, filter, sort and locale state and removes page 1', () => {
  const href='/zh/library?filter=favorite&sort=added&dir=desc&page=2';
  assert.equal(filmPageHref(href,3),'/zh/library?filter=favorite&sort=added&dir=desc&page=3');
  assert.equal(filmPageHref('/search?q=Le+Samoura%C3%AF&page=2',1),'/search?q=Le+Samoura%C3%AF');
});
test('malformed, repeated and oversized page parameters stay bounded', () => {
  for (const input of [undefined,'-2','0','Infinity','1.5','2e3']) assert.equal(normalizeFilmPage(input),1);
  assert.equal(normalizeFilmPage(['2','9']),2);
  assert.equal(normalizeFilmPage('99999999999999999999'),25001);
});
