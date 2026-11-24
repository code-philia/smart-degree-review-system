import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { resolveLoginVariant } from '../build/loginVariant.js';

const [selection, command, ...args] = process.argv.slice(2);
const variant = resolveLoginVariant(selection);
if (!['build', 'dev'].includes(command)) throw new Error('Expected build or dev');
const vite = fileURLToPath(new URL('../node_modules/vite/bin/vite.js', import.meta.url));
const result = spawnSync(process.execPath, [vite, ...(command === 'dev' ? [] : [command]), ...args], {
  stdio: 'inherit',
  env: { ...process.env, VITE_LOGIN_VARIANT: variant },
});
if (result.error) throw result.error;
process.exit(result.status ?? 1);
