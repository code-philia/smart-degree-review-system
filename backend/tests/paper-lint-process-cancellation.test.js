import { expect, it } from 'vitest';
import { createRequire } from 'node:module';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
const require = createRequire(import.meta.url);
const { runJsonProcess } = require('../src/normative/paperCompilerService');

it.skipIf(process.platform === 'win32')('terminates compiler descendants before cancellation completes', async () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'compiler-cancel-'));
  const marker = path.join(directory, 'child.pid');
  const controller = new AbortController();
  const childCode = 'process.on("SIGTERM",()=>{});setTimeout(()=>{},60000)';
  const parentCode = `const c=require('child_process').spawn(process.execPath,['-e',${JSON.stringify(childCode)}],{stdio:'inherit'});require('fs').writeFileSync(${JSON.stringify(marker)},String(c.pid));setTimeout(()=>{},60000)`;
  let pid;
  const work = runJsonProcess(process.execPath, ['-e', parentCode], { signal: controller.signal }).catch(error => error);
  try {
    for (let i = 0; i < 200 && !fs.existsSync(marker); i++) await new Promise(resolve => setTimeout(resolve, 10));
    expect(fs.existsSync(marker)).toBe(true);
    pid = Number(fs.readFileSync(marker, 'utf8'));
    controller.abort();
    expect((await work).code).toBe('COMPILER_INTERRUPTED');
    let running = false;
    try { process.kill(pid, 0); running = !fs.readFileSync(`/proc/${pid}/stat`, 'utf8').includes(') Z '); } catch {}
    expect(running).toBe(false);
  } finally {
    controller.abort();
    if (pid) { try { process.kill(pid, 'SIGKILL'); } catch {} }
    await work;
    fs.rmSync(directory, { recursive: true, force: true });
  }
});
