import assert from 'node:assert/strict';

export function record(metrics, name, value) {
  assert.ok(Number.isFinite(value) && value >= 0, name);
  (metrics[name] ??= []).push(value);
}

export async function timed(metrics, name, work) {
  const start = performance.now();
  const result = await work();
  record(metrics, name, performance.now() - start);
  return result;
}

export async function repeated(metrics, name, work, count = 25) {
  await work(); // One untimed warm-up on the same path.
  for (let i = 0; i < count; i++) await timed(metrics, name, work);
}

export function summarize(metrics) {
  return Object.fromEntries(
    Object.entries(metrics).map(([name, samples]) => {
      const sorted = [...samples].sort((a, b) => a - b);
      const n = sorted.length;
      const round = (x) => Number(x.toFixed(2));
      return [
        name,
        {
          n,
          median: round((sorted[Math.floor((n - 1) / 2)] + sorted[Math.floor(n / 2)]) / 2),
          p95: n >= 20 ? round(sorted[Math.ceil(0.95 * n) - 1]) : null,
          max: round(sorted[n - 1]),
          samples: samples.map(round),
        },
      ];
    }),
  );
}
