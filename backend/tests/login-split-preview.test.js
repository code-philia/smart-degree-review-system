import express from 'express';
import request from 'supertest';
import { createServer } from 'node:http';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { afterEach, beforeEach, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { createSplitPreviewApp } = require('../src/loginSplitPreview');
let root, server, app;
const publicOrigin = 'http://121.36.247.138:3003';
const apiPublicOrigin = 'http://121.36.247.138:3000';

beforeEach(async () => {
  root = mkdtempSync(path.join(tmpdir(), 'login-split-preview-'));
  writeFileSync(path.join(root, 'index.html'), '<title>Formal login</title>');
  writeFileSync(path.join(root, 'login-variant.json'), JSON.stringify({ schema_version: 1, variant: 'split' }));
  const upstream = express();
  upstream.use(express.raw({ type: () => true }));
  upstream.all('/api/probe', (req, res) => res.set('Set-Cookie', ['one=1; HttpOnly', 'two=2; SameSite=Lax']).status(201).json({
    path: req.originalUrl, method: req.method, body: req.body?.toString(),
    host: req.headers.host, origin: req.headers.origin, cookie: req.headers.cookie,
  }));
  upstream.get('/api/missing', (_req, res) => res.status(404).json({ missing: true }));
  server = createServer(upstream);
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  app = createSplitPreviewApp({ frontendDistPath: root, upstreamPort: server.address().port,
    publicOrigin, apiPublicOrigin, revision: 'reviewed-revision' });
});

afterEach(async () => {
  if (server?.listening) await new Promise(resolve => server.close(resolve));
  if (root && path.dirname(root) === tmpdir() && path.basename(root).startsWith('login-split-preview-')) rmSync(root, { recursive: true });
});

it('streams original API path, body, cookies and status to the fixed public backend', async () => {
  const response = await request(app).post('/api/probe?item=2').set('Host', new URL(publicOrigin).host)
    .set('Origin', publicOrigin).set('Cookie', 'arc_session=test').type('application/octet-stream').send('unchanged bytes').expect(201);
  expect(response.body).toEqual({ path: '/api/probe?item=2', method: 'POST', body: 'unchanged bytes',
    host: new URL(apiPublicOrigin).host, origin: apiPublicOrigin, cookie: 'arc_session=test' });
  expect(response.headers['set-cookie']).toEqual(['one=1; HttpOnly', 'two=2; SameSite=Lax']);
});

it('does not translate an unrelated browser origin into an allowed origin', async () => {
  const response = await request(app).get('/api/probe').set('Host', new URL(publicOrigin).host)
    .set('Origin', 'https://unrelated.example').expect(201);
  expect(response.body.origin).toBe('https://unrelated.example');
});

it('retains API 404 responses instead of serving the SPA', async () => {
  const response = await request(app).get('/api/missing').expect(404);
  expect(response.body).toEqual({ missing: true });
});

it('serves the formal frontend and a separate version without caching HTML', async () => {
  const response = await request(app).get('/auth').expect(200);
  expect(response.text).toContain('Formal login');
  expect(response.headers.link).toContain('/login-thesis-v2.png');
  expect(response.headers.link).not.toContain('login-campus');
  expect(response.headers['cache-control']).toContain('no-store');
  expect((await request(app).get('/__preview-version').expect(200)).body).toEqual({ branch: 'feat/login-v2-split', revision: 'reviewed-revision' });
  await request(app).get('/assets/missing.js').expect(404);
});

it('returns 502 if the existing backend is unavailable', async () => {
  await new Promise(resolve => server.close(resolve));
  await request(app).get('/api/probe').expect(502);
});

it('rejects the private administrator port and invalid upstream ports', () => {
  for (const upstreamPort of [3002, 0, 65536, NaN]) {
    expect(() => createSplitPreviewApp({ frontendDistPath: root, upstreamPort, publicOrigin, apiPublicOrigin })).toThrow();
  }
});
