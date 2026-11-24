// Install the pinned official Firefox into this audit's directory. Do not alter
// Windows components or the shared Edge/WebKit browser cache.
const { spawnSync } = require('node:child_process');
const path = require('node:path');
const { OUT } = require('./paths.cjs');
const cli = path.join(path.dirname(require.resolve('playwright/package.json')), 'cli.js');
const result = spawnSync(process.execPath, [cli, 'install', 'firefox'], {
  stdio: 'inherit', windowsHide: true,
  env: { ...process.env, PLAYWRIGHT_BROWSERS_PATH: path.join(OUT, 'firefox-runtime') },
});
if (result.error) console.error(result.error.message);
process.exitCode = result.status ?? 1;
