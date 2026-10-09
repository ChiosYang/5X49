import assert from 'node:assert/strict';
import test from 'node:test';
import { execFileSync } from 'node:child_process';

test('all today defaults follow the local calendar across UTC, year and DST boundaries', () => {
  const cases = [
    ['Asia/Shanghai','2026-10-08T18:00:00Z','2026-10-09'],
    ['Asia/Shanghai','2026-12-31T16:00:00Z','2027-01-01'],
    ['America/Los_Angeles','2027-01-01T03:00:00Z','2026-12-31'],
    ['America/New_York','2026-03-08T07:01:00Z','2026-03-08'],
    ['UTC','2026-02-28T23:59:59Z','2026-02-28'],
  ];
  for (const [zone, instant, expected] of cases) {
    const output = execFileSync(process.execPath, ['--disable-warning=MODULE_TYPELESS_PACKAGE_JSON','--experimental-strip-types','--input-type=module','-e',
      `import {todayLocalDate,createViewingDateDraft} from './src/lib/diary.ts'; const now=new Date('${instant}'); console.log(JSON.stringify([todayLocalDate(now),createViewingDateDraft(null,now).dateValue]));`],
      {cwd:new URL('../..',import.meta.url),env:{...process.env,TZ:zone},encoding:'utf8'});
    assert.deepEqual(JSON.parse(output),[expected,expected],zone);
  }
});
