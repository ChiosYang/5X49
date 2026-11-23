import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const [baselinePath, currentPath] = process.argv.slice(2);
if (!baselinePath || !currentPath) {
  throw Error('Usage: node e2e/performance/compare.mjs <baseline.json> <current.json>');
}
const [baseline, current] = await Promise.all(
  [baselinePath, currentPath].map(async (file) => JSON.parse(await readFile(file, 'utf8'))),
);
for (const report of [baseline, current]) {
  assert.ok(report.complete && report.schema === 1, 'Expected a complete v1 performance report');
}
assert.equal(current.workloadSha256, baseline.workloadSha256, 'Performance workload changed');
assert.deepEqual(current.fixture, baseline.fixture, 'Fixture configuration changed');
assert.deepEqual(
  current.tiers.map((t) => t.films),
  baseline.tiers.map((t) => t.films),
  'Library sizes differ',
);

for (const field of [
  'platform',
  'cpu',
  'logicalCpus',
  'memoryGiB',
  'node',
  'chromium',
  'pythonAndSqlite',
  'ffmpeg',
]) {
  if (current[field] !== baseline[field]) console.error('Environment changed:', field);
}
console.log('films\tmetric\tstatistic\tbaseline\tcurrent\tchange_pct');
function row(films, metric, statistic, before, after) {
  const delta = before === 0 ? 'n/a' : ((after / before - 1) * 100).toFixed(1);
  console.log([films, metric, statistic, before, after, delta].join('\t'));
}
for (const [index, before] of baseline.tiers.entries()) {
  const after = current.tiers[index];
  for (const [name, attempt] of Object.entries(before.scans)) {
    console.error(`${before.films} films, ${name}: ${attempt.status} → ${after.scans[name].status}`);
  }
  const allMetrics = new Set([...Object.keys(before.metrics), ...Object.keys(after.metrics)]);
  for (const name of allMetrics) {
    if (!before.metrics[name] || !after.metrics[name]) {
      assert.ok(name === 'job.initial-scan' || name === 'job.repeat-scan', 'Missing metric: ' + name);
      console.error('Successful scan timing unavailable in one run:', name);
    }
  }
  for (const [metric, reference] of Object.entries(before.metrics)) {
    const measured = after.metrics[metric];
    if (!measured) continue;
    assert.equal(reference.n, measured.n, metric + ' sample count differs');
    row(before.films, metric, 'median_ms', reference.median, measured.median);
    if (reference.p95 !== null) row(before.films, metric, 'p95_ms', reference.p95, measured.p95);
  }
  for (const load of before.load) {
    const match = after.load.find((item) => item.clients === load.clients && item.requests === load.requests);
    assert.ok(match, 'Load mix differs');
    row(before.films, 'load.' + load.clients + '-clients', 'requests_per_second', load.rps, match.rps);
  }
}
