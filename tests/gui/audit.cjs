const { spawnSync } = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');
const { OUT } = require('./paths.cjs');
const cli = path.join(path.dirname(require.resolve('playwright/package.json')), 'cli.js');
const config = path.join(__dirname, 'playwright.config.cjs');
const phases = [];
function execute(phase, args) {
  const result = spawnSync(process.execPath, [cli, 'test', '--config', config, ...args], {
    stdio: 'inherit', env: { ...process.env, GUI_PHASE: phase }, windowsHide: true,
  });
  phases.push({ phase, exitCode: result.status ?? 1, error: result.error?.message });
}
execute('read', ['--project', 'chromium-desktop', '--project', 'chromium-mobile', '--project', 'firefox-desktop', '--project', 'webkit-desktop']);
// Read-only product failures must not silently skip an explicitly approved lifecycle.
if (process.env.GUI_ALLOW_LIVE_WRITES === '1' && process.env.GUI_ALLOW_EMAIL === '1') {
  execute('live', ['--project', 'live-lifecycle', '--no-deps']);
} else console.log('Live writes skipped: both GUI_ALLOW_LIVE_WRITES=1 and GUI_ALLOW_EMAIL=1 are required.');
fs.writeFileSync(path.join(OUT, 'runner-results.json'), JSON.stringify(phases, null, 2));
process.exitCode = phases.some(p => p.exitCode) ? 1 : 0;
