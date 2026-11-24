// Independent frontend entry. Deliberately does not import app, auth, database or workers.
const express = require('express');
const http = require('node:http');
const path = require('node:path');
const { registerFrontendStatic } = require('./frontendStatic');

function endToEndHeaders(input) {
  const headers = { ...input };
  const blocked = ['connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
    'te', 'trailer', 'transfer-encoding', 'upgrade',
    ...String(input.connection || '').toLowerCase().split(',').map(value => value.trim())];
  for (const name of blocked) delete headers[name];
  return headers;
}

function createSplitPreviewApp({ frontendDistPath, upstreamPort = 3000,
  publicOrigin, apiPublicOrigin, revision = 'unknown' }) {
  if (!Number.isInteger(upstreamPort) || upstreamPort < 1 || upstreamPort > 65535 || upstreamPort === 3002) {
    throw new Error('Use the public API listener, never the private administrator port');
  }
  const preview = new URL(publicOrigin);
  const api = new URL(apiPublicOrigin);
  if (preview.protocol !== 'http:' || api.protocol !== 'http:') throw new Error('Expected HTTP entry points');
  const app = express();
  app.disable('x-powered-by');
  app.get('/__preview-version', (_req, res) => {
    res.set('Cache-Control', 'no-store').json({ branch: 'feat/login-v2-split', revision });
  });
  app.use((req, res, next) => {
    if (!/^\/api(?:\/|\?|$)/.test(req.url)) return next();
    const headers = endToEndHeaders(req.headers);
    for (const name of Object.keys(headers)) {
      if (name === 'forwarded' || name.startsWith('x-forwarded-')) delete headers[name];
    }
    // Only our own entry translates origin. Unrelated origins retain the backend's checks.
    if (headers.origin === preview.origin && headers.host === preview.host) headers.origin = api.origin;
    headers.host = api.host;
    const upstream = http.request({ hostname: '127.0.0.1', port: upstreamPort,
      method: req.method, path: req.url, headers, timeout: 30 * 60 * 1000 }, response => {
      res.writeHead(response.statusCode, endToEndHeaders(response.headers));
      response.on('error', () => res.destroy());
      response.pipe(res);
    });
    upstream.on('error', () => {
      if (res.headersSent) return res.destroy();
      res.status(502).set('Cache-Control', 'no-store').end('Backend unavailable');
    });
    upstream.on('timeout', () => upstream.destroy());
    req.on('aborted', () => upstream.destroy());
    res.on('close', () => { if (!res.writableEnded) upstream.destroy(); });
    req.pipe(upstream);
  });
  registerFrontendStatic(app, frontendDistPath);
  return app;
}

if (require.main === module) {
  const port = Number(process.env.PORT || 3003);
  if (!Number.isInteger(port) || port < 1024 || port > 65535 || [3000, 3001, 3002].includes(port)) {
    throw new Error('Choose a separate, unprivileged preview port');
  }
  const app = createSplitPreviewApp({
    frontendDistPath: path.resolve(__dirname, '../../frontend/dist'),
    publicOrigin: process.env.PREVIEW_PUBLIC_ORIGIN || 'http://121.36.247.138:3003',
    apiPublicOrigin: process.env.API_PUBLIC_ORIGIN || 'http://121.36.247.138:3000',
    revision: process.env.RELEASE_SHA,
  });
  const server = app.listen(port, '0.0.0.0', () => console.log(`Formal login frontend listening on ${port}`));
  process.on('SIGTERM', () => {
    server.close(() => process.exit(0));
    setTimeout(() => process.exit(1), 10_000).unref();
  });
}

module.exports = { createSplitPreviewApp };
