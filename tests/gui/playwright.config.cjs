const { defineConfig, devices } = require('@playwright/test');
const { OUT, BASE } = require('./paths.cjs');
const path = require('node:path');
const fs = require('node:fs');
const phase = process.env.GUI_PHASE || 'read';
const edge = { browserName: 'chromium', channel: 'msedge', viewport: { width: 1440, height: 1000 } };
// This audit pins Playwright 1.57.0 / Firefox revision 1497. Use its isolated
// official installation when present; keep Edge and WebKit on their own defaults.
const isolatedFirefox = process.env.GUI_FIREFOX_EXECUTABLE || path.join(OUT, 'firefox-runtime', 'firefox-1497', 'firefox', 'firefox.exe');
const firefoxLaunch = fs.existsSync(isolatedFirefox) ? { executablePath: isolatedFirefox } : {};
module.exports = defineConfig({
  testDir: './specs', testMatch: '**/*.spec.cjs',
  timeout: 60_000, expect: { timeout: 12_000 },
  workers: 2, fullyParallel: true, retries: 0,
  globalSetup: './setup.cjs', globalTeardown: './teardown.cjs',
  outputDir: path.join(OUT, 'artifacts', phase),
  reporter: [['line'], ['json', { outputFile: path.join(OUT, phase + '-results.json') }], ['html', { outputFolder: path.join(OUT, 'html', phase), open: 'never' }]],
  use: { baseURL: BASE, locale: 'zh-CN', timezoneId: 'Asia/Shanghai', colorScheme: 'light',
    actionTimeout: 15_000, navigationTimeout: 35_000, acceptDownloads: true,
    trace: 'off', screenshot: 'only-on-failure', video: 'off', serviceWorkers: 'block' },
  projects: [
    { name: 'chromium-desktop', testMatch: /(?:public|admin|student|reports|errors)\.spec\.cjs$/, use: edge },
    { name: 'chromium-mobile', testMatch: /responsive\.spec\.cjs$/, use: { ...edge, viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } },
    { name: 'firefox-desktop', testMatch: /cross-browser\.spec\.cjs$/, use: { browserName: 'firefox', launchOptions: firefoxLaunch, viewport: { width: 1440, height: 1000 } } },
    { name: 'webkit-desktop', testMatch: /cross-browser\.spec\.cjs$/, use: { browserName: 'webkit', viewport: { width: 1440, height: 1000 } } },
    { name: 'live-lifecycle', testMatch: /lifecycle\.spec\.cjs$/, dependencies: ['chromium-desktop', 'chromium-mobile', 'firefox-desktop', 'webkit-desktop'], use: edge },
  ],
});
