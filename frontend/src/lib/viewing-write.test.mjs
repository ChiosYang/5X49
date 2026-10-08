import assert from 'node:assert/strict';
import test from 'node:test';
import { commitViewingWrite } from './viewing-write.ts';

test('commits exact new ID before refreshing; read failure cannot become write failure', async () => {
  const events = [];
  const result = await commitViewingWrite(async () => ({id: 'new-second-viewing'}),
    value => events.push(value.id), async () => { events.push('refresh'); throw Error('offline'); });
  assert.deepEqual(events, ['new-second-viewing', 'refresh']);
  assert.equal(result.value.id, 'new-second-viewing');
  assert.equal(result.refreshFailed, true);
});
test('write failure neither records a receipt nor refreshes', async () => {
  let calls = 0;
  await assert.rejects(commitViewingWrite(async () => { throw Error('write failed'); },
    () => calls++, async () => calls++), /write failed/);
  assert.equal(calls, 0);
});
test('same-day deliberate writes each retain their distinct ID', async () => {
  const receipts = [];
  for (const id of ['first', 'second']) {
    await commitViewingWrite(async () => ({id, watched_at:'2026-10-08'}), v => receipts.push(v.id), async () => {});
  }
  assert.deepEqual(receipts, ['first', 'second']);
});

test('explicit refresh rejects HTTP failures and retry only reads, preserving the committed ID', async () => {
  const { refreshViewingReadCaches } = await import('./viewing-write.ts');
  let writes = 0;
  let reads = 0;
  let fail = true;
  let receipt;
  const cache = new Map([['viewings', ['old-viewing']]]);
  const refresh = () => refreshViewingReadCaches(['viewings'], async () => {
    reads++;
    if (fail) throw Error('GET 500');
    return ['old-viewing', 'new-viewing'];
  }, async (key, pendingRead) => { const value = await pendingRead; cache.set(key, value); });
  const result = await commitViewingWrite(async () => { writes++; return { id:'new-viewing' }; },
    value => { receipt = value; }, refresh);
  assert.equal(result.refreshFailed, true);
  assert.equal(receipt.id, 'new-viewing');
  assert.deepEqual(cache.get('viewings'), ['old-viewing']);
  fail = false;
  await refresh();
  assert.equal(writes, 1);
  assert.equal(reads, 2);
  assert.deepEqual(cache.get('viewings'), ['old-viewing', 'new-viewing']);
});
