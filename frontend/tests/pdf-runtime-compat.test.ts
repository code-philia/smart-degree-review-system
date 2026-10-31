import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { expect, it } from 'vitest';

it('parses a real PDF without modern byte, Promise and URL built-ins', async () => {
  const features = [[Uint8Array.prototype, 'toHex'], [Uint8Array.prototype, 'toBase64'], [Promise, 'try'], [Promise, 'withResolvers'], [URL, 'parse']] as const;
  const originals = features.map(([object, key]) => Object.getOwnPropertyDescriptor(object, key));
  let task: { destroy: () => Promise<void> } | undefined;
  try {
    for (const [object, key] of features) Object.defineProperty(object, key, { value: undefined, configurable: true, writable: true });
    const { loadPdfJs } = await import('../src/pdfRuntime');
    const pdfjs = await loadPdfJs();
    for (const [object, key] of features) expect(typeof (object as unknown as Record<string, unknown>)[key]).toBe('function');
    const require = createRequire(import.meta.url);
    pdfjs.GlobalWorkerOptions.workerSrc = pathToFileURL(require.resolve('pdfjs-dist/legacy/build/pdf.worker.mjs')).href;
    const objects = ['<< /Type /Catalog /Pages 2 0 R >>', '<< /Type /Pages /Kids [3 0 R] /Count 1 >>', '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>', '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>', '<< /Length 45 >>\nstream\nBT /F1 12 Tf 10 100 Td (Compatibility) Tj ET\nendstream'];
    let contents = '%PDF-1.4\n';
    const offsets: number[] = [];
    objects.forEach((object, index) => { offsets.push(contents.length); contents += `${index + 1} 0 obj\n${object}\nendobj\n`; });
    const xref = contents.length;
    contents += `xref\n0 6\n0000000000 65535 f \n${offsets.map(offset => String(offset).padStart(10, '0') + ' 00000 n \n').join('')}trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`;
    const loading = pdfjs.getDocument({ data: new TextEncoder().encode(contents), useSystemFonts: true });
    task = loading;
    const pdf = await loading.promise;
    expect(pdf.numPages).toBe(1);
    const page = await pdf.getPage(1);
    const text = await page.getTextContent();
    expect(text.items.filter(item => 'str' in item).map(item => 'str' in item ? item.str : '').join('')).toBe('Compatibility');
  } finally {
    await task?.destroy();
    features.forEach(([object, key], index) => {
      const descriptor = originals[index];
      if (descriptor) Object.defineProperty(object, key, descriptor);
      else Reflect.deleteProperty(object, key);
    });
  }
});
