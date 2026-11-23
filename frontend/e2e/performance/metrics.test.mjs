import assert from 'node:assert/strict';
import test from 'node:test';
import { repeated, summarize, timed } from './metrics.mjs';

test('report uses the median and nearest-rank P95, preserving acquisition order', () => {
  const values = Array.from({ length: 20 }, (_, i) => 20 - i);
  const result = summarize({ workload: values, short: [7] });
  assert.equal(result.workload.median, 10.5);
  assert.equal(result.workload.p95, 19);
  assert.equal(result.workload.max, 20);
  assert.deepEqual(result.workload.samples, values);
  assert.equal(result.short.p95, null);
});

test('warm-up and failed operations do not become successful timing samples', async () => {
  let calls = 0;
  const metrics = {};
  await repeated(metrics, 'read', async () => ++calls, 3);
  assert.equal(calls, 4);
  assert.equal(metrics.read.length, 3);
  await assert.rejects(
    timed(metrics, 'failed', async () => {
      throw Error('fixture');
    }),
  );
  assert.equal(metrics.failed, undefined);
});
