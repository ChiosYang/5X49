import assert from 'node:assert/strict';
import test from 'node:test';
import { readLibraryRanges, invalidLibraryRanges, clearLibraryFilters } from './library-filters.ts';
import { buildLibraryHref, appendLibraryFilters } from './library-care.ts';
import { filmPageHref } from './film-pagination.ts';
import { matchesLibraryFilter } from './library-interactions.ts';

const state = {view:'all',sort:'duration',direction:'desc',filter:'watched',favorite:true,
  query:'Range & 中文',duration_min:'90',duration_max:'120',rating_min:'3',rating_max:'5',year_min:'1999',year_max:'2001',page:3};

test('all conditions survive care navigation, pagination and URL serialization', () => {
  const href = buildLibraryHref(state);
  const params = new URL(href, 'http://localhost').searchParams;
  assert.equal(params.get('q'), state.query);
  assert.equal(params.get('filter'), 'watched');
  assert.equal(params.get('favorite'), 'true');
  assert.deepEqual(readLibraryRanges(Object.fromEntries(params)), {
    duration_min:'90',duration_max:'120',rating_min:'3',rating_max:'5',year_min:'1999',year_max:'2001'});
  const care = new URL(buildLibraryHref(state, 'metadata'), 'http://localhost').searchParams;
  assert.equal(care.get('page'), '3');
  assert.equal(care.has('metadata_page'), false);
  assert.equal(care.get('duration_min'), '90');
  const next = new URL(filmPageHref(href, 4), 'http://localhost').searchParams;
  assert.equal(next.get('page'), '4');
  next.set('page', '3');
  assert.equal(next.toString(), params.toString());
  assert.equal(appendLibraryFilters(new URLSearchParams(), state).get('year_max'), '2001');
});

test('metadata pagination keeps the Film page independent and returning drops only maintenance state', () => {
  const maintenance = {...state, view:'metadata', metadataPage:2};
  const params = new URL(buildLibraryHref(maintenance), 'http://localhost').searchParams;
  assert.equal(params.get('page'), '3');
  assert.equal(params.get('metadata_page'), '2');
  assert.equal(params.get('q'), state.query);
  assert.equal(params.get('rating_max'), '5');
  assert.equal(buildLibraryHref(maintenance, 'all'), buildLibraryHref(state));
  const previous = new URL(buildLibraryHref({...maintenance, metadataPage:1}), 'http://localhost').searchParams;
  assert.equal(previous.get('page'), '3');
  assert.equal(previous.has('metadata_page'), false);
});

test('one-sided and inclusive equal bounds are valid; malformed, fractional and reversed ranges are explicit errors', () => {
  assert.deepEqual(invalidLibraryRanges({duration_min:'90',duration_max:'90',year_max:'2100'}), []);
  for (const value of ['0','-1','10001','90.1','1e2','NaN','Infinity','abc'])
    assert.deepEqual(invalidLibraryRanges({duration_min:value}), ['duration']);
  assert.deepEqual(invalidLibraryRanges({duration_min:'100',duration_max:'90',year_min:'2101'}), ['duration','year']);
  assert.equal(readLibraryRanges({year_min:[' 1999 ','2001']}).year_min, '1999');
  assert.deepEqual(invalidLibraryRanges({rating_min:'1',rating_max:'5'}), []);
  for (const value of ['0','6','1.5','NaN']) assert.deepEqual(invalidLibraryRanges({rating_min:value}), ['rating']);
  assert.deepEqual(invalidLibraryRanges({rating_min:'5',rating_max:'3'}), ['rating']);
});

test('clear removes every condition and page while retaining sort and care view', () => {
  assert.deepEqual(clearLibraryFilters(state), {view:'all',sort:'duration',direction:'desc',filter:'all',page:1});
  assert.equal(buildLibraryHref(clearLibraryFilters(state)), '/library?sort=duration&dir=desc');
});

test('local profile updates honor favorite AND watched status', () => {
  assert.equal(matchesLibraryFilter({watched:true,favorite:false}, 'watched', true), false);
  assert.equal(matchesLibraryFilter({watched:false,favorite:true}, 'watched', true), false);
  assert.equal(matchesLibraryFilter({watched:true,favorite:true}, 'watched', true), true);
  assert.equal(matchesLibraryFilter({watched:true,favorite:true,rating:null}, 'watched', true, 1, 5), false);
  assert.equal(matchesLibraryFilter({watched:true,favorite:true,rating:3}, 'watched', true, 3, 3), true);
  assert.equal(matchesLibraryFilter({watched:true,favorite:true,rating:2}, 'watched', true, 3), false);
  assert.equal(matchesLibraryFilter({watched:true,favorite:true,rating:4}, 'watched', true, undefined, 3), false);
});
