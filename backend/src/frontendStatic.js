const express = require('express');
const path = require('path');
const { compressedAssets } = require('./compressedAssets');

function resourceNotFound(_req, res) {
  res.status(404).type('text').send('Not found');
}

function registerFrontendStatic(app, frontendDistPath) {
  const staticOptions = { index: false, redirect: false };
  const assetsPath = path.join(frontendDistPath, 'assets');
  app.get(/^\/auth\/?$/i, (_req, res, next) => {
    // Preload the preferred format only; unsupported browsers use the picture fallback.
    res.append('Link', '</login-campus-B-v5-750f63ec.avif>; rel=preload; as=image; type="image/avif"; fetchpriority=high');
    next();
  });
  app.use('/assets', compressedAssets(assetsPath), express.static(assetsPath, staticOptions), resourceNotFound);
  app.use('/pdfjs-resources', express.static(path.join(frontendDistPath, 'pdfjs-resources'), {
    ...staticOptions,
    maxAge: 31536000000,
    immutable: true,
  }), resourceNotFound);
  app.use('/pdfjs-cmaps', express.static(path.join(frontendDistPath, 'pdfjs-cmaps'), staticOptions), resourceNotFound);

  app.use(express.static(frontendDistPath, {
    setHeaders(res, file) {
      if (path.extname(file) === '.html') res.set('Cache-Control', 'no-store');
      else if (/-[a-f0-9]{8,}\.(?:png|jpe?g|webp|avif)$/i.test(path.basename(file))) {
        // A changed image gets a new content-hashed URL; keep its bytes intact.
        res.set('Cache-Control', 'public, max-age=31536000, immutable');
      }
    },
  }));

  // Resource misses have already returned 404; only application routes reach the SPA.
  app.get(/^(?!\/api(?:\/|$)).*/, (_req, res) => {
    res.set('Cache-Control', 'no-store');
    res.sendFile(path.join(frontendDistPath, 'index.html'), { cacheControl: false });
  });
}

module.exports = { registerFrontendStatic };
