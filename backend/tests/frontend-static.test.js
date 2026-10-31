import express from 'express';
import request from 'supertest';
import { gzipSync } from 'node:zlib';
import { mkdirSync, mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { afterEach, beforeEach, expect, it } from 'vitest';

const require = createRequire(import.meta.url);
const { registerFrontendStatic } = require('../src/frontendStatic');

const html = '<!doctype html><title>Frontend fixture</title><div id="root">SPA fixture</div>';
const workerText = 'const worker = "PDF viewer";\n'.repeat(1000);
let root;
let app;

function binaryResponse(response, done) {
  const chunks = [];
  response.on('data', (chunk) => chunks.push(chunk));
  response.on('end', () => done(null, Buffer.concat(chunks)));
  response.on('error', done);
}

beforeEach(() => {
  root = mkdtempSync(path.join(tmpdir(), 'frontend-static-'));
  const files = {
    'index.html': html,
    'assets/worker-hash.js': workerText,
    'assets/worker-hash.js.gz': gzipSync(workerText),
    'pdfjs-resources/5.4.624/cmaps/GBK-EUC-H.bcmap': Buffer.from('cmap fixture'),
    'pdfjs-resources/5.4.624/standard_fonts/FoxitSans.pfb': Buffer.from('font fixture'),
    'pdfjs-resources/5.4.624/wasm/openjpeg.wasm': Buffer.from('wasm fixture'),
    'pdfjs-cmaps/GBK-EUC-H.bcmap': Buffer.from('legacy cmap fixture'),
  };
  for (const [name, content] of Object.entries(files)) {
    const file = path.join(root, name);
    mkdirSync(path.dirname(file), { recursive: true });
    writeFileSync(file, content);
  }
  app = express();
  app.get('/api/health', (_req, res) => res.json({ ready: true }));
  registerFrontendStatic(app, root);
});

afterEach(() => {
  if (!root) return;
  const target = path.resolve(root);
  if (path.dirname(target) !== path.resolve(tmpdir()) || !path.basename(target).startsWith('frontend-static-')) {
    throw new Error('Unexpected frontend fixture cleanup path');
  }
  rmSync(target, { recursive: true, force: true });
});

it.each([
  '/assets/missing-worker.js',
  '/assets',
  '/pdfjs-resources/5.4.624/cmaps/missing.bcmap',
  '/pdfjs-resources',
  '/pdfjs-cmaps/missing.bcmap',
  '/pdfjs-cmaps',
])('returns 404 instead of SPA HTML for missing resource %s', async (url) => {
  const response = await request(app).get(url).expect(404);
  expect(response.text).not.toContain('SPA fixture');
});

it.each(['/', '/index.html', '/thirty-rules-check/history'])('prevents stale application HTML at %s', async (url) => {
  const response = await request(app).get(url).expect(200);
  expect(response.text).toBe(html);
  expect(response.headers['cache-control']).toMatch(/no-store/);
});

it.each([
  ['cmaps/GBK-EUC-H.bcmap', 'cmap fixture'],
  ['standard_fonts/FoxitSans.pfb', 'font fixture'],
  ['wasm/openjpeg.wasm', 'wasm fixture'],
])('caches versioned PDF resource %s immutably with an ETag', async (resource, content) => {
  const url = `/pdfjs-resources/5.4.624/${resource}`;
  const response = await request(app).get(url).buffer(true).parse(binaryResponse).expect(200);
  expect(response.body).toEqual(Buffer.from(content));
  expect(response.headers['cache-control']).toBe('public, max-age=31536000, immutable');
  expect(response.headers.etag).toBeTruthy();
  await request(app).get(url).set('If-None-Match', response.headers.etag).expect(304);
});

it('retains the legacy CMap URL', async () => {
  const response = await request(app).get('/pdfjs-cmaps/GBK-EUC-H.bcmap').expect(200);
  expect(response.body).toEqual(Buffer.from('legacy cmap fixture'));
});

it('preserves compressed JavaScript delivery and its uncompressed fallback', async () => {
  const compressed = await request(app).get('/assets/worker-hash.js').set('Accept-Encoding', 'gzip').expect(200);
  expect(compressed.headers['content-encoding']).toBe('gzip');
  expect(compressed.headers['content-type']).toMatch(/javascript/);
  expect(compressed.headers.vary).toContain('Accept-Encoding');
  expect(compressed.text).toBe(workerText);
  const plain = await request(app).get('/assets/worker-hash.js').set('Accept-Encoding', 'identity').expect(200);
  expect(plain.headers['content-encoding']).toBeUndefined();
  expect(plain.text).toBe(workerText);
});

it('keeps API requests outside the SPA fallback', async () => {
  const health = await request(app).get('/api/health').expect(200);
  expect(health.body).toEqual({ ready: true });
  for (const url of ['/api', '/api/missing']) {
    const response = await request(app).get(url).expect(404);
    expect(response.text).not.toContain('SPA fixture');
  }
});
