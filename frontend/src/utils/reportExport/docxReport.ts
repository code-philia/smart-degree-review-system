import { reportBlocks, stripExportControls, type ExportReport } from './model';
import { flowWordSourceText } from './wordSourceFlow';

/** Native editable paragraphs mirror the article used by the XeLaTeX export. */
export async function createWordReport(model: ExportReport): Promise<Blob> {
  const {
    Document,
    Paragraph,
    TextRun,
    Packer,
    Footer,
    AlignmentType,
    PageNumber,
    HeadingLevel,
    BorderStyle,
    LineRuleType,
  } = await import('docx');
  const reports = [model];
  const blocks = reportBlocks(model),
    scopeStart = blocks.findIndex((block) => block.role === 'scope');
  const scopeCounts = new Set(
    model.rules.map((rule) =>
      model.language === 'en'
        ? `This check records ${rule.finding_count} ${rule.finding_count === 1 ? 'result' : 'results'}.`
        : `本项记录 ${rule.finding_count} 项检测结果。`,
    ),
  );
  const sourceCorrections = model.findings
    .flatMap((finding) => (finding.source_suggestion_indices || []).map((index) => finding.suggestions[index]))
    .filter((text) => Boolean(text) && /[\r\n]/.test(text));
  const font = {
    ascii: 'Latin Modern Roman',
    hAnsi: 'Latin Modern Roman',
    eastAsia: 'Noto Serif CJK SC',
    cs: 'Latin Modern Roman',
  };
  const children = reports.flatMap((report) =>
    blocks.map((block, index) => {
      const title = block.kind === 'title',
        heading = block.kind === 'heading',
        subheading = block.kind === 'subheading';
      const signature = ['signature', 'signature_school', 'website'].includes(block.role || '');
      const quote = block.kind === 'quote';
      const prose = block.kind === 'text' || block.kind === 'notice';
      const keepWithScopeCount =
        scopeStart >= 0 &&
        index > scopeStart &&
        block.kind === 'text' &&
        scopeCounts.has(blocks[index + 1]?.text || '');
      const sourceSnippet =
        block.kind === 'text' && /^(?:(?:疑似错别字|疑似错字)[：:]|Suspected typo:)/i.test(block.text);
      const sourceCorrection = block.role === 'advice' && sourceCorrections.some((text) => block.text.includes(text));
      const flow = quote || sourceSnippet || sourceCorrection ? flowWordSourceText(block.text) : null;
      const text = flow?.text ?? block.text;
      const size = title ? 44 : heading ? 28 : 24;
      const run = (text: string, marked = false, bold = title || heading || subheading) =>
        stripExportControls(text)
          .replace(/\r\n?/g, '\n')
          .split('\n')
          .map(
            (part, index) =>
              new TextRun({
                text: part,
                break: index ? 1 : 0,
                font,
                size,
                bold,
                color: marked ? '96354A' : '202A35',
                shading: marked ? { fill: 'F6E6BE' } : undefined,
                language: {
                  value: report.language === 'en' ? 'en-US' : 'zh-CN',
                  eastAsia: report.language === 'en' ? 'en-US' : 'zh-CN',
                },
              }),
          );
      const runs = [];
      if (block.sourceLabel) runs.push(...run(block.sourceLabel + '  '));
      let cursor = 0;
      // Validate original offsets, then map the display-only highlight after reflow.
      for (const mark of (block.marks || [])
        .filter(
          (mark) =>
            Number.isInteger(mark.start) &&
            Number.isInteger(mark.end) &&
            mark.start >= 0 &&
            mark.end > mark.start &&
            mark.end <= block.text.length,
        )
        .map((mark) => ({ start: flow?.offsets[mark.start] ?? mark.start, end: flow?.offsets[mark.end] ?? mark.end }))
        .filter((mark) => mark.end > mark.start)
        .sort((a, b) => a.start - b.start)) {
        if (mark.start < cursor) continue;
        runs.push(...run(text.slice(cursor, mark.start)), ...run(text.slice(mark.start, mark.end), true));
        cursor = mark.end;
      }
      const suffix = block.status ? ` (${block.status})` : '';
      if (subheading && suffix && text.endsWith(suffix)) {
        runs.push(...run(text.slice(cursor, -suffix.length)), ...run(suffix, false, false));
      } else runs.push(...run(text.slice(cursor)));
      return new Paragraph({
        heading: title
          ? HeadingLevel.TITLE
          : heading
            ? HeadingLevel.HEADING_1
            : subheading
              ? HeadingLevel.HEADING_2
              : undefined,
        children: runs,
        alignment: title ? AlignmentType.CENTER : prose ? AlignmentType.JUSTIFIED : AlignmentType.LEFT,
        indent: quote ? { left: 480, right: 480, firstLine: 0 } : { firstLine: prose ? 480 : 0 },
        spacing: {
          line: title ? 600 : 400,
          lineRule: LineRuleType.EXACT,
          before: block.role === 'signature' ? 520 : heading ? 320 : subheading ? 240 : 0,
          after: title ? 160 : signature ? 40 : block.role === 'document' || block.role === 'metadata' ? 60 : 120,
        },
        keepNext:
          title ||
          heading ||
          subheading ||
          block.role === 'signature' ||
          block.role === 'signature_school' ||
          block.role === 'document' ||
          block.role === 'metadata' ||
          keepWithScopeCount,
        widowControl: true,
        border: quote ? { left: { style: BorderStyle.SINGLE, size: 6, color: 'BBC4CF', space: 7 } } : undefined,
      });
    }),
  );
  const document = new Document({
    compatibility: { doNotExpandShiftReturn: true },
    creator: model.language === 'en' ? 'Smart Degree · AI Review Assistant' : '智慧学位 AI 评阅辅助系统',
    title: model.language === 'en' ? 'Thesis compliance report' : '论文规范性检测报告',
    styles: {
      default: {
        document: {
          run: { font, size: 24, color: '202A35' },
          paragraph: { spacing: { line: 400, lineRule: LineRuleType.EXACT } },
        },
      },
      paragraphStyles: [
        {
          id: 'Title',
          name: 'Title',
          basedOn: 'Normal',
          next: 'Normal',
          run: { font, size: 44, bold: true },
          paragraph: { keepNext: true, alignment: AlignmentType.CENTER },
        },
        {
          id: 'Heading1',
          name: 'Heading 1',
          basedOn: 'Normal',
          next: 'Normal',
          run: { font, size: 28, bold: true },
          paragraph: { keepNext: true, outlineLevel: 0 },
        },
        {
          id: 'Heading2',
          name: 'Heading 2',
          basedOn: 'Normal',
          next: 'Normal',
          run: { font, size: 24, bold: true },
          paragraph: { keepNext: true, outlineLevel: 1 },
        },
      ],
    },
    sections: [
      {
        properties: {
          page: { size: { width: 11906, height: 16838 }, margin: { top: 1304, right: 1417, bottom: 1304, left: 1417 } },
        },
        footers: {
          default: new Footer({
            children: [
              new Paragraph({
                alignment: AlignmentType.CENTER,
                children: [new TextRun({ children: [PageNumber.CURRENT], font, size: 24 })],
              }),
            ],
          }),
        },
        children,
      },
    ],
  });
  return Packer.toBlob(document);
}
