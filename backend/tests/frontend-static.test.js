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
const approvedBackground = Buffer.from('unchanged approved PNG bytes');
const backgroundPath = '/login-campus-B-v5-b25c6008.png';
const avifPath = '/login-campus-B-v5-750f63ec.avif';
const webpPath = '/login-campus-B-v5-229caf6d.webp';
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
    [backgroundPath.slice(1)]: approvedBackground,
    [avifPath.slice(1)]: Buffer.from('approved AVIF bytes'),
    [webpPath.slice(1)]: Buffer.from('approved WebP bytes'),
    'login-schoolmark.jpg': Buffer.from('school mark fixture'),
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


it('caches the approved background without changing bytes or range delivery', async () => {
  const response = await request(app).get(backgroundPath).buffer(true).parse(binaryResponse).expect(200);
  expect(response.body).toEqual(approvedBackground);
  expect(response.headers['cache-control']).toBe('public, max-age=31536000, immutable');
  expect(response.headers.etag).toBeTruthy();
  await request(app).get(backgroundPath).set('If-None-Match', response.headers.etag).expect(304);
  const partial = await request(app).get(backgroundPath).set('Range', 'bytes=0-8').buffer(true).parse(binaryResponse).expect(206);
  expect(partial.body).toEqual(approvedBackground.subarray(0, 9));
  const unversioned = await request(app).get('/login-schoolmark.jpg').expect(200);
  expect(unversioned.headers['cache-control']).not.toContain('immutable');
});

it.each(['/auth', '/AUTH', '/auth/', '/auth?return_to=%2Fpaper-upload'])('preloads only typed AVIF from the sign-in response at %s', async (url) => {
  const response = await request(app).get(url).expect(200);
  expect(response.text).toBe(html);
  expect(response.headers.link).toBe(`<${avifPath}>; rel=preload; as=image; type="image/avif"; fetchpriority=high`);
  expect(response.headers['cache-control']).toMatch(/no-store/);
});

it('does not preload a login illustration for workspace pages or API responses', async () => {
  for (const url of ['/paper-upload', '/reports', '/api/health']) {
    const response = await request(app).get(url).expect(200);
    expect(response.headers.link).toBeUndefined();
  }
});


it.each([[avifPath,'image/avif','approved AVIF bytes'],[webpPath,'image/webp','approved WebP bytes']])('serves %s immutably with its actual image type and range support',async(url,type,bytes)=>{
  const response=await request(app).get(url).buffer(true).parse(binaryResponse).expect(200);
  expect(response.headers['content-type']).toBe(type);
  expect(response.headers['cache-control']).toBe('public, max-age=31536000, immutable');
  expect(response.body).toEqual(Buffer.from(bytes));
  await request(app).get(url).set('If-None-Match',response.headers.etag).expect(304);
  const partial=await request(app).get(url).set('Range','bytes=0-7').buffer(true).parse(binaryResponse).expect(206);
  expect(partial.body).toEqual(Buffer.from(bytes).subarray(0,8));
});
