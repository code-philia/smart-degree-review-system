import { expect, it } from 'vitest';
import { Blob as NodeBlob } from 'node:buffer';
import { unzipSync, strFromU8 } from 'fflate';
import { buildExportReport, reportBlocks, reportText, reportMarkdown } from '../src/utils/reportExport/model';
import { createReportFile } from '../src/utils/reportExport/formats';
import { fixture } from './fixtures/reportExport';
import { collectExportTranslationTexts } from '../src/utils/reportExport/presentation';
import { addTranslations } from '../src/i18n/locale.js';
import { clearReportTranslations } from '../src/i18n/reportTranslations';
it('puts actionable findings before the full rule catalog without dropping source material', () => {
  const model = buildExportReport(fixture, [], null),
    before = JSON.stringify(model);
  const text = reportText(model);
  expect(text.indexOf('2 检测发现与修改建议')).toBeLessThan(text.indexOf('3 检测范围与执行情况'));
  expect(text).toContain('规则未实现警告');
  expect(reportBlocks(model).some((b) => b.role === 'advice')).toBe(true);
  for (const value of ['原文证据', '第二处证据', '已有本地建议', '引用证据']) expect(text).toContain(value);
  expect(JSON.stringify(model)).toBe(before);
  expect(reportMarkdown(model)).toContain('修改建议：已有本地建议');
});
it('uses native editable Word heading styles and readable prose instead of a flat list of runs', async () => {
  const oldBlob = globalThis.Blob;
  globalThis.Blob = NodeBlob as any;
  try {
    addTranslations(
      Object.fromEntries(
        collectExportTranslationTexts(buildExportReport(fixture, [], null)).map((text, index) => [
          text,
          `English explanation ${index}.`,
        ]),
      ),
    );
    const file = await createReportFile(buildExportReport(fixture, [], null), 'docx');
    const xml = strFromU8(unzipSync(new Uint8Array(await file.blob.arrayBuffer()))['word/document.xml']);
    expect(xml).toContain('w:val="Title"');
    expect(xml).toContain('w:val="Heading1"');
    expect(xml).toContain('w:val="Heading2"');
    expect(xml).toContain('w:widowControl');
  } finally {
    globalThis.Blob = oldBlob;
    clearReportTranslations();
  }
});
