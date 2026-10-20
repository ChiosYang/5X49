import test from 'node:test';
import assert from 'node:assert/strict';
import { minuteTime, parseTime, parseHealthLocation, videoHealthHref } from './video-health.ts';

test('UTC schedule fields round-trip without local date or DST conversion', () => {
  for (const value of [0, 59, 60, 1439]) assert.equal(parseTime(minuteTime(value)), value);
  assert.equal(minuteTime(1320), '22:00');
});
test('empty, malformed and out-of-range schedule values cannot be submitted', () => {
  for (const value of ['', '24:00', '12:60', '1:00', '2026-10-14', '00:0', '00:00Z']) assert.equal(parseTime(value), null);
});
test('inspection filter, page and selected record survive URL round trips', () => {
  const location = { filter: 'all', offset: 20, selected: 'health_abc-123' };
  const href = videoHealthHref('section=video-checks&context=library', location);
  const url = new URL(href, 'https://5x49.local');
  assert.equal(url.searchParams.get('context'), 'library');
  assert.deepEqual(parseHealthLocation(url.searchParams), location);
  assert.equal(url.hash, '#video-health');
  assert.equal(new URL(videoHealthHref(url.search, { ...location, selected: null }), url).searchParams.has('health_file'), false);
});
test('inspection URL rejects malformed filters, offsets and record paths', () => {
  assert.deepEqual(parseHealthLocation(new URLSearchParams('health_state=bogus&health_offset=-20&health_file=../file')), { filter: 'abnormal', offset: 0, selected: null });
  assert.equal(parseHealthLocation(new URLSearchParams('health_offset=Infinity')).offset, 0);
  assert.equal(parseHealthLocation(new URLSearchParams('health_offset=999999999999999999999')).offset, 0);
});
