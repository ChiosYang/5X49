import assert from 'node:assert/strict';
import test from 'node:test';
import { executeFilmAction } from './viewing-write.ts';
import { ApiError } from './fetcher.ts';

test('write failure is consumed, reports a safe cause and leaves saved state intact', async () => {
  let state = false, reads = 0;
  const result = await executeFilmAction(async () => { throw new ApiError('private provider URL', 503); },
    () => { state = true; }, async () => { reads++; });
  assert.deepEqual(result, {status:'failed', reason:'unavailable'});
  assert.equal(state, false);
  assert.equal(reads, 0);
});
test('committed favorite survives refresh failure; refresh retry never resends PUT', async () => {
  let writes = 0, reads = 0, state = false;
  const refresh = async () => { if (++reads === 1) throw new TypeError('offline'); };
  const result = await executeFilmAction(async () => { writes++; return {favorite:true}; },
    value => { state = value.favorite; }, refresh);
  assert.equal(result.status, 'refreshFailed');
  assert.equal(state, true);
  await refresh();
  assert.equal(writes, 1);
  assert.equal(reads, 2);
});
test('network, conflict and rejected writes remain distinct without leaking error text', async () => {
  for (const [error, reason] of [[new TypeError('network'), 'connection'], [new ApiError('private',409),'conflict'], [new ApiError('private',422),'rejected']]) {
    assert.deepEqual(await executeFilmAction(async () => { throw error; }, () => assert.fail(), async () => assert.fail()),
      {status:'failed', reason});
  }
});
