import assert from 'node:assert/strict';
import test from 'node:test';
import { createSettingsScanGuard, settingsScanBlocked, subscribeSettingsScanGuard } from './settings-scan-guard.ts';

test('drafts block immediately and releasing an unsent page clears only its own guard', () => {
  const first = createSettingsScanGuard(), second = createSettingsScanGuard();
  const seen = []; const stop = subscribeSettingsScanGuard(() => seen.push(settingsScanBlocked()));
  first.setDraft(true); second.setDraft(true); first.release(); assert.equal(settingsScanBlocked(), true);
  second.release(); assert.equal(settingsScanBlocked(), false); assert.deepEqual(seen, [true, false]); stop();
});

test('save guard survives leaving Settings and clears after the request settles', () => {
  const guard = createSettingsScanGuard(); guard.setDraft(true); guard.setSaving(true); guard.release();
  guard.setDraft(false); assert.equal(settingsScanBlocked(), true); guard.setSaving(false); assert.equal(settingsScanBlocked(), false);
  guard.acquire(); guard.setDraft(true); assert.equal(settingsScanBlocked(), true); guard.release(); assert.equal(settingsScanBlocked(), false);
});
