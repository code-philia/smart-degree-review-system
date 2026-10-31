import type { ReportBlock } from './model';
export type ExportLine = {
  text: string;
  y: number;
  fontSize: number;
  lineHeight: number;
  bold: boolean;
  color: string;
  indent: number;
};
export type ExportPage = { lines: ExportLine[] };
export const PAGE = { pageWidth: 1240, pageHeight: 1754, margin: 88, top: 150, bottom: 105 };
const styles = {
  title: { size: 40, height: 58, gap: 22, bold: true, color: '#172d49' },
  heading: { size: 30, height: 46, gap: 14, bold: true, color: '#1e3a5f' },
  subheading: { size: 25, height: 39, gap: 10, bold: true, color: '#263b55' },
  meta: { size: 22, height: 34, gap: 8, bold: false, color: '#596a7b' },
  text: { size: 24, height: 37, gap: 14, bold: false, color: '#263747' },
  quote: { size: 22, height: 35, gap: 12, bold: false, color: '#596a7b' },
  notice: { size: 22, height: 35, gap: 16, bold: false, color: '#73624a' },
};

function* wrappedLines(text: string, width: number, measure: (text: string) => number): Generator<string> {
  for (const paragraph of text.replace(/\r\n?/g, '\n').split('\n')) {
    if (!paragraph) {
      yield '';
      continue;
    }
    const chars = Array.from(paragraph);
    for (let offset = 0; offset < chars.length;) {
      const remaining = chars.length - offset;
      let low = 1,
        high = Math.min(64, remaining);
      const fits = (length: number) => measure(chars.slice(offset, offset + length).join('')) <= width;
      while (high < remaining && fits(high)) {
        low = high;
        high = Math.min(remaining, high * 2);
      }
      while (low < high) {
        const middle = Math.ceil((low + high) / 2);
        if (fits(middle)) low = middle;
        else high = middle - 1;
      }
      yield chars.slice(offset, offset + low).join('');
      offset += low;
    }
  }
}
export const wrapText = (text: string, width: number, measure: (text: string) => number) =>
  Array.from(wrappedLines(text, width, measure));

export function* paginateReportSteps(
  blocks: ReportBlock[],
  measure: (text: string, size: number, bold: boolean) => number,
  options: typeof PAGE = PAGE,
): Generator<void, ExportPage[]> {
  const { pageWidth, pageHeight, margin, top, bottom } = options,
    maxY = pageHeight - bottom;
  const pages: ExportPage[] = [{ lines: [] }];
  let y = top;
  const next = () => {
    pages.push({ lines: [] });
    y = top;
  };
  let work = 0;
  for (const block of blocks) {
    const style = styles[block.kind],
      indent = block.kind === 'quote' ? 18 : 0;
    const lines = wrappedLines(block.text, pageWidth - margin * 2 - indent, (text) =>
      measure(text, style.size, style.bold),
    );
    if (
      (block.kind === 'heading' || block.kind === 'subheading') &&
      y + style.height * 3 > maxY &&
      pages.at(-1)!.lines.length
    )
      next();
    for (const text of lines) {
      if (y + style.height > maxY && pages.at(-1)!.lines.length) next();
      pages
        .at(-1)!
        .lines.push({
          text,
          y,
          fontSize: style.size,
          lineHeight: style.height,
          bold: style.bold,
          color: style.color,
          indent,
        });
      y += style.height;
      if (++work >= 32) {
        work = 0;
        yield;
      }
    }
    y += style.gap;
  }
  return pages;
}
export function paginateReport(
  blocks: ReportBlock[],
  measure: (text: string, size: number, bold: boolean) => number,
  options: typeof PAGE = PAGE,
): ExportPage[] {
  const steps = paginateReportSteps(blocks, measure, options);
  let result = steps.next();
  while (!result.done) result = steps.next();
  return result.value;
}
