import test from 'node:test';
import assert from 'node:assert/strict';
import { minuteTime, parseTime } from './video-health.ts';

test('UTC schedule fields round-trip without local date or DST conversion', () => {
  for (const value of [0, 59, 60, 1439]) assert.equal(parseTime(minuteTime(value)), value);
  assert.equal(minuteTime(1320), '22:00');
});
test('empty, malformed and out-of-range schedule values cannot be submitted', () => {
  for (const value of ['', '24:00', '12:60', '1:00', '2026-10-14', '00:0', '00:00Z']) assert.equal(parseTime(value), null);
});
