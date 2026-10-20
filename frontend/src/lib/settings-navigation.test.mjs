import assert from 'node:assert/strict';
import test from 'node:test';
import { canonicalSettingsHref, legacySettingsHref, resolveSettingsLocation, settingSections, settingsHref } from './settings-navigation.ts';

test('settings categories keep the requested order and stable canonical destinations', () => {
  assert.deepEqual(settingSections, ['general', 'library', 'connections', 'library-maintenance', 'video-checks', 'diagnostics', 'backup', 'cleanup']);
  for (const section of settingSections) assert.equal(canonicalSettingsHref(`section=${section}`), settingsHref(section));
  assert.equal(canonicalSettingsHref('section=unknown'), settingsHref('general'));
  assert.equal(canonicalSettingsHref('section=integrations&context=library'), '/settings?section=connections&context=library');
});
test('legacy settings anchors resolve to their functional category without dropping query context', () => {
  assert.deepEqual(resolveSettingsLocation('library', '#danger-zone'), { section: 'cleanup', anchor: 'danger-zone' });
  assert.equal(canonicalSettingsHref('section=maintenance', '#backup-heading'), '/settings?section=backup#backup-download');
  assert.equal(canonicalSettingsHref('section=maintenance', '#restore'), '/settings?section=backup#restore');
  assert.equal(canonicalSettingsHref('section=library', '#video-health-settings'), '/settings?section=library#video-health-settings');
  assert.equal(canonicalSettingsHref('section=maintenance'), '/settings?section=diagnostics');
});
test('legacy manager and health entry points preserve review, results, backup and runtime destinations', () => {
  assert.equal(legacySettingsHref('manage'), '/settings?section=library-maintenance');
  assert.equal(legacySettingsHref('manage', '#video-health', 'health_state=all&health_offset=20'), '/settings?health_state=all&health_offset=20&section=video-checks#video-health');
  assert.equal(legacySettingsHref('manage', '#backup-heading'), '/settings?section=backup#backup-download');
  assert.equal(legacySettingsHref('manage', '#metadata-reviews'), '/library?view=metadata');
  assert.equal(legacySettingsHref('manage', '#root-video-reviews'), '/library?view=inbox');
  assert.equal(legacySettingsHref('health'), '/settings?section=diagnostics');
  assert.equal(legacySettingsHref('manage', '#watcher', 'context=library'), '/settings?context=library&section=diagnostics#runtime');
});
