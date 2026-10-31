import { Blob as NodeBlob } from 'node:buffer';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { unzipSync, strFromU8 } from 'fflate';
import { buildExportReport } from '../src/utils/reportExport/model';
import { createReportFile, downloadReportFile } from '../src/utils/reportExport/formats';
import { fixture } from './fixtures/reportExport';

beforeEach(() => vi.stubGlobal('Blob', NodeBlob));
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.useRealTimers();
});
it('creates genuine Unicode Markdown, TXT and JSON files', async () => {
  const model = buildExportReport(fixture, [], null);
  for (const [format, extension] of [
    ['markdown', '.md'],
    ['text', '.txt'],
    ['json', '.json'],
  ] as const) {
    const file = await createReportFile(model, format);
    expect(file.filename).toMatch(new RegExp(extension.replace('.', '\\.') + '$'));
    const text = await file.blob.text();
    expect(text).toContain('中文');
    if (format === 'json') expect(JSON.parse(text).findings).toHaveLength(1);
    else expect(text).toContain('检测结果仅供参考');
  }
});
it('creates a valid editable DOCX ZIP with every finding and line break', async () => {
  const file = await createReportFile(buildExportReport(fixture, [], null), 'docx');
  const files = unzipSync(new Uint8Array(await file.blob.arrayBuffer()));
  expect(files['[Content_Types].xml']).toBeTruthy();
  const xml = strFromU8(files['word/document.xml']);
  for (const value of ['论文规范性检测报告', '已有本地建议', '第二行', '第二处证据']) expect(xml).toContain(value);
  expect(xml).toContain('<w:br/>');
  expect(xml).toContain('&lt;script&gt;');
});
it('honors cancellation before allocating any export resources', async () => {
  const controller = new AbortController();
  controller.abort();
  await expect(
    createReportFile(buildExportReport(fixture, [], null), 'pdf', { signal: controller.signal }),
  ).rejects.toMatchObject({ name: 'AbortError' });
});
it('releases download URLs and temporary links', () => {
  vi.useFakeTimers();
  const create = vi.fn(() => 'blob:test-export'),
    revoke = vi.fn();
  vi.stubGlobal(
    'URL',
    class extends URL {
      static createObjectURL = create;
      static revokeObjectURL = revoke;
    },
  );
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  downloadReportFile({ filename: '论文.txt', blob: new Blob(['内容']) });
  expect(document.querySelector('a[download]')).toBeNull();
  vi.runAllTimers();
  expect(revoke).toHaveBeenCalledWith('blob:test-export');
});
