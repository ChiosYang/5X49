import assert from 'node:assert/strict';
import { record, timed } from './metrics.mjs';

const measuredRepeats = 20;

export async function measureBrowser(browser, origin, film, metrics) {
  for (const width of [1440, 390]) {
    const context = await browser.newContext({
      baseURL: origin,
      viewport: { width, height: 900 },
      hasTouch: width === 390,
    });
    try {
      // Routing disables Chromium's HTTP cache. Keep the same policy across all runs.
      await context.route('**/*', (route) =>
        new URL(route.request().url()).origin === origin ? route.continue() : route.abort('blockedbyclient'),
      );
      const pages = [
        ['library', '/en/library', '[id^="film-link-"]'],
        ['detail', '/en/library/' + film.id, '#film-graph-title'],
        ['explore', '/en/explore', 'main input[type=search]:enabled'],
        ['diary', '/en/diary', '[id^="viewing-link-"]'],
        ['dna', '/en/diary?view=dna', 'main section dl dd'],
        ['activity', '/en/library/activity', 'main ol li button'],
        ['settings', '/en/settings?section=general', 'main button[aria-pressed]:enabled'],
      ];
      for (const [name, url, selector] of pages) {
        for (let i = 0; i <= measuredRepeats; i++) {
          const page = await context.newPage();
          try {
            const start = performance.now();
            const response = await page.goto(url, { waitUntil: 'domcontentloaded' });
            assert.ok(response?.ok(), name);
            await page.locator(selector).first().waitFor({ state: 'visible', timeout: 30000 });
            await page.evaluate(
              () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))),
            );
            const ready = performance.now() - start;
            const ttfb = await page.evaluate(
              () => performance.getEntriesByType('navigation')[0].responseStart,
            );
            await page.waitForFunction(
              () => performance.getEntriesByName('first-contentful-paint').length > 0,
            );
            const fcp = await page.evaluate(
              () => performance.getEntriesByName('first-contentful-paint')[0].startTime,
            );
            if (i > 0) {
              record(metrics, `ui.${width}.${name}.ready`, ready);
              record(metrics, `ui.${width}.${name}.ttfb`, ttfb);
              record(metrics, `ui.${width}.${name}.fcp`, fcp);
            }
          } finally {
            await page.close();
          }
        }
      }

      const page = await context.newPage();
      for (let i = 0; i <= measuredRepeats; i++) {
        const samples = i === 0 ? {} : metrics;
        const query = new URLSearchParams({
          q: film.title,
          year_min: String(film.year),
          year_max: String(film.year),
        });
        await page.goto('/en/library?' + query);
        const filter = page.getByRole('button', { name: 'Filter', exact: true });
        await filter.waitFor();
        await timed(samples, `ui.${width}.open-filter`, async () => {
          await filter.click();
          await page.getByRole('dialog').getByRole('button', { name: 'Apply filters' }).waitFor();
        });
        await page.keyboard.press('Escape');
        const card = page.locator(`a.library-card-title[href$="/${film.id}"]`);
        await card.scrollIntoViewIfNeeded();
        await timed(samples, `ui.${width}.open-detail`, async () => {
          await card.click();
          await page.getByRole('dialog').locator('#film-graph-title').waitFor();
        });
        await timed(samples, `ui.${width}.return-library`, async () => {
          await page.keyboard.press('Escape');
          await page.getByRole('dialog').waitFor({ state: 'hidden' });
          await card.waitFor();
          assert.equal(new URL(page.url()).searchParams.get('q'), film.title);
        });
        await page.goto('/en/explore');
        const input = page.locator('main input[type=search]:enabled');
        await input.fill('The Quiet Signal');
        await timed(samples, `ui.${width}.submit-search`, async () => {
          await input.press('Enter');
          await page.locator('#search-films-title').waitFor();
          await page.locator('a.library-card-title').first().waitFor();
          assert.equal(new URL(page.url()).searchParams.get('q'), 'The Quiet Signal');
        });
      }
      await page.close();
    } finally {
      await context.close();
    }
  }
}
