import { reportBlocks, reportMarkdown, reportText, safeReportFilename, type ExportReport } from './model';
import { canvasPng, checkCancelled, renderReportPages, type ExportProgress } from './renderPages';

export type ReportExportFormat = 'pdf' | 'markdown' | 'text' | 'docx' | 'image' | 'json';
export type ExportFile = { blob: Blob; filename: string };
type Options = { signal?: AbortSignal; onProgress?: ExportProgress };

export async function createReportFile(
  model: ExportReport,
  format: ReportExportFormat,
  { signal, onProgress }: Options = {},
): Promise<ExportFile> {
  checkCancelled(signal);
  const stem = safeReportFilename(model.document.filename);
  if (format === 'markdown')
    return { filename: stem + '.md', blob: new Blob([reportMarkdown(model)], { type: 'text/markdown;charset=utf-8' }) };
  if (format === 'text')
    return {
      filename: stem + '.txt',
      blob: new Blob(['\uFEFF', reportText(model)], { type: 'text/plain;charset=utf-8' }),
    };
  if (format === 'json')
    return {
      filename: stem + '.json',
      blob: new Blob([JSON.stringify(model, null, 2)], { type: 'application/json;charset=utf-8' }),
    };
  if (format === 'docx') {
    onProgress?.('正在生成可编辑 Word 文档');
    const { Document, Paragraph, TextRun, Packer, Header, Footer, AlignmentType, PageNumber } = await import('docx');
    checkCancelled(signal);
    const children = reportBlocks(model).map((block) => {
      const title = block.kind === 'title',
        heading = block.kind === 'heading',
        subheading = block.kind === 'subheading';
      const lines = block.text.replace(/\r\n?/g, '\n').split('\n');
      return new Paragraph({
        children: lines.map(
          (text, index) =>
            new TextRun({
              text,
              break: index ? 1 : 0,
              bold: title || heading || subheading,
              size: title ? 38 : heading ? 30 : subheading ? 25 : 22,
              color: title || heading ? '1E3A5F' : block.kind === 'notice' ? '73624A' : '263747',
            }),
        ),
        spacing: { before: heading ? 220 : subheading ? 140 : 0, after: title ? 280 : heading ? 140 : 120, line: 320 },
        keepNext: title || heading || subheading,
        indent: block.kind === 'quote' ? { left: 240 } : undefined,
      });
    });
    const document = new Document({
      creator: '智慧学位 AI 评阅辅助系统',
      title: '论文规范性检测报告',
      styles: { default: { document: { run: { font: 'Microsoft YaHei', size: 22 } } } },
      sections: [
        {
          properties: {
            page: {
              size: { width: 11906, height: 16838 },
              margin: { top: 1100, right: 1100, bottom: 1100, left: 1100 },
            },
          },
          headers: {
            default: new Header({
              children: [
                new Paragraph({
                  children: [new TextRun({ text: '智慧学位 · 论文规范性检测报告', size: 18, color: '64748B' })],
                }),
              ],
            }),
          },
          footers: {
            default: new Footer({
              children: [
                new Paragraph({
                  alignment: AlignmentType.CENTER,
                  children: [
                    new TextRun({ text: '检测结果仅供参考 · ', size: 18, color: '64748B' }),
                    new TextRun({ children: [PageNumber.CURRENT], size: 18, color: '64748B' }),
                  ],
                }),
              ],
            }),
          },
          children,
        },
      ],
    });
    const blob = await Packer.toBlob(document);
    checkCancelled(signal);
    return { blob, filename: stem + '.docx' };
  }
  if (format === 'pdf') {
    onProgress?.('正在准备 PDF');
    const { jsPDF } = await import('jspdf');
    checkCancelled(signal);
    const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4', compress: true });
    pdf.setProperties({
      title: '论文规范性检测报告',
      subject: model.document.filename,
      author: '智慧学位 AI 评阅辅助系统',
    });
    for await (const { canvas, index } of renderReportPages(model, signal, onProgress)) {
      if (index) pdf.addPage();
      pdf.addImage(canvas, 'PNG', 0, 0, 210, 297, undefined, 'FAST');
    }
    checkCancelled(signal);
    return { filename: stem + '.pdf', blob: pdf.output('blob') };
  }
  if (format === 'image') {
    const images: Record<string, Uint8Array> = {};
    let single: Blob | null = null;
    for await (const { canvas, index, total } of renderReportPages(model, signal, onProgress)) {
      const blob = await canvasPng(canvas);
      checkCancelled(signal);
      if (total === 1) single = blob;
      else images[`${stem}_${String(index + 1).padStart(3, '0')}.png`] = new Uint8Array(await blob.arrayBuffer());
    }
    if (single) return { filename: stem + '.png', blob: single };
    onProgress?.('正在打包全部报告图片');
    const { zipSync } = await import('fflate');
    checkCancelled(signal);
    // PNGs are already compressed; storing avoids a costly redundant compression pass.
    const bytes = zipSync(images, { level: 0 });
    return {
      filename: stem + '_图片.zip',
      blob: new Blob([new Uint8Array(bytes).buffer], { type: 'application/zip' }),
    };
  }
  throw new Error('暂不支持此导出格式');
}

export function downloadReportFile({ blob, filename }: ExportFile) {
  const url = URL.createObjectURL(blob),
    anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.hidden = true;
  document.body.appendChild(anchor);
  try {
    anchor.click();
  } finally {
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}
