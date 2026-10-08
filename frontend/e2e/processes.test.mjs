import test from 'node:test';
import assert from 'node:assert/strict';
import { managedProcesses } from './processes.mjs';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';

test('failed server spawn rejects readiness and remains safely stoppable', async () => {
  const root = await mkdtemp(path.join(tmpdir(), '5x49-process-test-'));
  const p = managedProcesses({}, root);
  try {
    const child = p.start(path.join(root, 'missing-executable'), [], root, 'server.log');
    await assert.rejects(p.ready('http://127.0.0.1:1', child), /ENOENT/);
    await assert.rejects(p.finish(child), /ENOENT/);
    await p.stop(child);
    assert.equal(p.children.size, 0);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test('cleanup stops an owned process, including signal termination', async () => {
  const p = managedProcesses({}, tmpdir());
  const child = p.start(process.execPath, ['-e', 'setInterval(() => {}, 1000)'], tmpdir());
  try {
    await p.stop(child);
    await assert.rejects(p.finish(child), /Process exited/);
    assert.equal(p.children.size, 0);
  } finally { await p.stop(child); }
});
