import workerUrl from 'pdfjs-dist/legacy/build/pdf.worker.min.mjs?url';

type PdfJs = typeof import('pdfjs-dist/legacy/build/pdf.mjs');
let runtime: Promise<PdfJs> | null = null;

/** Core and worker must use the same polyfilled build and package version. */
export function loadPdfJs(): Promise<PdfJs> {
  if (!runtime) {
    runtime = import('pdfjs-dist/legacy/build/pdf.mjs').then((pdfjs) => {
      pdfjs.GlobalWorkerOptions.workerPort = null;
      pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;
      return pdfjs;
    }).catch((error) => {
      runtime = null;
      throw error;
    });
  }
  return runtime;
}

export function pdfResourceOptions(version: string) {
  // Blob workers have no HTTP base URL for resolving root-relative font fetches.
  const base = new URL(`${import.meta.env.BASE_URL}pdfjs-resources/${version}/`, globalThis.location?.href || 'http://localhost/').href;
  return { cMapUrl: `${base}cmaps/`, cMapPacked: true, standardFontDataUrl: `${base}standard_fonts/`, wasmUrl: `${base}wasm/` };
}
