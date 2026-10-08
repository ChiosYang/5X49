import test from 'node:test';
import assert from 'node:assert/strict';
import { matchesLibraryFilter, shouldRefreshLibraryEvent } from './library-interactions.ts';
test('local mutations remove only films that no longer match the active filter', () => {
  assert.equal(matchesLibraryFilter({watched:true,favorite:false},'unwatched'),false);
  assert.equal(matchesLibraryFilter({watched:true,favorite:true},'favorite'),true);
  assert.equal(matchesLibraryFilter({watched:true,favorite:false},'all'),true);
});
test('library changes reconcile detail-originating mutations, malformed events do not refresh', () => {
  assert.equal(shouldRefreshLibraryEvent('profile_state_updated'),true);
  assert.equal(shouldRefreshLibraryEvent('viewing_created'),true);
  assert.equal(shouldRefreshLibraryEvent('scan_complete'),true);
  assert.equal(shouldRefreshLibraryEvent(undefined),false);
});
