const express = require('express');
const path = require('path');
const { compressedAssets } = require('./compressedAssets');

function resourceNotFound(_req, res) {
  res.status(404).type('text').send('Not found');
}

function registerFrontendStatic(app, frontendDistPath) {
  const staticOptions = { index: false, redirect: false };
  const assetsPath = path.join(frontendDistPath, 'assets');
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
    },
  }));

  // Resource misses have already returned 404; only application routes reach the SPA.
  app.get(/^(?!\/api(?:\/|$)).*/, (_req, res) => {
    res.set('Cache-Control', 'no-store');
    res.sendFile(path.join(frontendDistPath, 'index.html'), { cacheControl: false });
  });
}

module.exports = { registerFrontendStatic };
