const express = require('express');

function compressedAssets(root) {
  const compressed = express.static(root, {
    maxAge: 31536000000,
    immutable: true,
    setHeaders(res, file) {
      res.set('Content-Encoding', 'gzip');
      res.type(file.endsWith('.css.gz') ? 'css' : 'js');
    },
  });
  return (req, res, next) => {
    if (!['GET', 'HEAD'].includes(req.method) || !/\.(?:m?js|css)$/.test(req.path)) return next();
    res.vary('Accept-Encoding');
    if (!req.acceptsEncodings('gzip') || req.headers.range) return next();
    const original = req.url;
    const query = original.indexOf('?');
    req.url = query < 0 ? original + '.gz' : original.slice(0, query) + '.gz' + original.slice(query);
    compressed(req, res, (error) => {
      req.url = original;
      next(error);
    });
  };
}

module.exports = { compressedAssets };
