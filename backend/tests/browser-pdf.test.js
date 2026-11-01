import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import express from 'express';
import request from 'supertest';
import { afterEach, expect, it, vi } from 'vitest';

const require = createRequire(import.meta.url);
const { browserPdfPath, prepareBrowserPdf } = require('../src/normative/browserPdf');
const { sendPrivatePdf } = require('../src/normative/privatePdfResponse');
let hasQpdf = false;
try { execFileSync('qpdf', ['--version'], { stdio: 'ignore' }); hasQpdf = true; } catch {}
let directory;
afterEach(async () => {
  vi.unstubAllEnvs();
  if (directory) await fs.rm(directory, { recursive: true, force: true });
  directory = null;
});
async function sourcePdf() {
  directory = await fs.mkdtemp(path.join(os.tmpdir(), 'browser-pdf-'));
  const source = path.join(directory, 'paper.pdf');
  await fs.copyFile(path.resolve('tests/fixtures/local-four-rule-sample.pdf'), source);
  return source;
}
it.skipIf(!hasQpdf)('creates and reuses a linearized browser copy without rewriting the original PDF', async () => {
  const source = await sourcePdf();
  const original = await fs.readFile(source);
  const [first, second] = await Promise.all([prepareBrowserPdf(source), prepareBrowserPdf(source)]);
  expect(first).toBe(browserPdfPath(source));
  expect(path.extname(first)).not.toBe('.pdf');
  expect(second).toBe(first);
  const content = await fs.readFile(first);
  expect(content.subarray(0, 2048).toString()).toContain('/Linearized');
  expect(await fs.readFile(source)).toEqual(original);
  expect(execFileSync('qpdf', ['--show-npages', first], { encoding: 'utf8' })).toBe(execFileSync('qpdf', ['--show-npages', source], { encoding: 'utf8' }));
  const before = await fs.stat(first);
  expect(await prepareBrowserPdf(source)).toBe(first);
  expect((await fs.stat(first)).mtimeMs).toBe(before.mtimeMs);
  expect((await fs.readdir(directory)).filter(name => name.endsWith('.tmp'))).toEqual([]);
});
it.skipIf(!hasQpdf)('returns an already linearized original directly', async () => {
  const source = await sourcePdf();
  const linearized = path.join(directory, 'linearized.pdf');
  execFileSync('qpdf', ['--linearize', source, linearized]);
  expect(await prepareBrowserPdf(linearized)).toBe(linearized);
});
it('falls back to the original if the optimization tool is unavailable', async () => {
  const source = await sourcePdf();
  vi.stubEnv('ARC_QPDF_BINARY', path.join(directory, 'missing-qpdf'));
  expect(await prepareBrowserPdf(source)).toBe(source);
  expect((await fs.readdir(directory)).filter(name => name.endsWith('.tmp'))).toEqual([]);
});

it.skipIf(!hasQpdf)('streams byte ranges from the browser copy with private caching and the original filename', async () => {
  const source = await sourcePdf();
  const app = express();
  app.get('/pdf', (req, res, next) => sendPrivatePdf(req, res, source, '论文.pdf', next));
  const response = await request(app).get('/pdf').set('Range', 'bytes=0-2047').expect(206);
  expect(response.headers['content-type']).toMatch(/application\/pdf/);
  expect(response.headers['accept-ranges']).toBe('bytes');
  expect(response.headers['cache-control']).toBe('private, max-age=3600');
  expect(response.headers.vary).toContain('Cookie');
  expect(response.headers['content-disposition']).toContain(encodeURIComponent('论文.pdf'));
  expect(response.body.toString()).toContain('/Linearized');
});
