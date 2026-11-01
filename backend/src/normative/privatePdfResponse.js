const { prepareBrowserPdf } = require('./browserPdf');

async function sendPrivatePdf(req, res, pdfPath, filename, next) {
  const browserPath = await prepareBrowserPdf(pdfPath);
  if (res.destroyed) return;
  res.set('Content-Type', 'application/pdf');
  res.set('Content-Disposition', `inline; filename*=UTF-8''${encodeURIComponent(filename)}`);
  res.set('Cache-Control', 'private, max-age=3600');
  res.vary('Cookie');
  res.sendFile(browserPath, { acceptRanges: true, cacheControl: false, lastModified: true }, (error) => {
    if (!error) return;
    if (!res.headersSent) next(error);
    else res.destroy(error);
  });
}
module.exports = { sendPrivatePdf };
