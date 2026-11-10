import { describe, expect, it } from 'vitest';
import {
  buildExportReport,
  reportBlocks,
  reportMarkdown,
  reportText,
  safeReportFilename,
} from '../src/utils/reportExport/model';
import { paginateReport, wrapText } from '../src/utils/reportExport/layout';
import { fixture } from './fixtures/reportExport';

describe('report export model', () => {
  it('retains Unicode, counts, every location, evidence and existing suggestions across text formats', () => {
    const model = buildExportReport(fixture, [], {
      page_count: 20,
      word_count: 12345,
      text_available: true,
      counting_method: 'cjk_characters_and_words',
    });
    expect(model.summary.finding_count).toBe(1);
    expect(model.findings[0].locations.map((x) => x.page)).toEqual([3, 5]);
    const text = reportText(model);
    for (const value of [
      '中文论文<>.pdf',
      '2026-10-31 09:02:03',
      '12345',
      '原文证据',
      '第二处证据',
      '已有本地建议',
      '检查依据',
      '引用证据',
      '检测结果仅供参考',
    ])
      expect(text).toContain(value);
    expect(reportMarkdown(model)).toContain('&lt;script&gt;');
    expect(reportMarkdown(model)).toContain('\\*内容\\*');
    expect(JSON.parse(JSON.stringify(model)).findings).toHaveLength(1);
  });
  it('never presents unavailable rules as an all-clear or invents PDF word counts', () => {
    const report = {
      ...fixture,
      result: {
        ...fixture.result,
        summary: { ...fixture.result.summary, finding_count: 0, issue_rule_count: 0 },
        rule_runs: [{ ...fixture.result.rule_runs[0], outcome: 'inconclusive' as const, findings: [] }],
      },
    };
    const model = buildExportReport(report, [], null);
    expect(model.conclusion).toContain('无法判定');
    expect(model.document.word_count).toBeNull();
    expect(reportText(model)).toContain('未统计');
  });
  it('uses safe Windows filenames and keeps recognizable Chinese', () => {
    expect(safeReportFilename('中文<>:/\\论文.pdf')).toBe('中文_____论文_检测报告');
  });
  it('retains the new semantic report prerequisites, successful claims and numerical evidence', () => {
    const run = {
      ...fixture.result.rule_runs[0],
      rule_id: 'abstract_numeric_consistency_check',
      findings: [],
      params: {
        preconditions: [
          { id: 'abstract_numeric', passed: true },
          { id: 'contribution_mapping', passed: true },
          { id: 'experiment_subsection', passed: true },
        ],
        numeric_results: [
          {
            declaration_id: 'd1',
            declaration: { text: '准确率92.5%' },
            status: 'consistent',
            reason: '原始数据一致',
            evidence: [{ page: 8, quote: '实验准确率92.5%' }],
          },
        ],
      },
    };
    const model = buildExportReport({ ...fixture, result: { ...fixture.result, rule_runs: [run] } }, [], null);
    const output = reportText(model);
    for (const value of [
      '摘要数值型论点核验',
      '已通过',
      '准确率92.5%',
      '一致',
      '原始数据一致',
      '实验准确率92.5%',
      'PDF 第 8 页',
    ])
      expect(output).toContain(value);
    expect(model.rules[0].details.length).toBeGreaterThan(4);
    run.params.preconditions[0].passed = false;
    const failed = buildExportReport({ ...fixture, result: { ...fixture.result, rule_runs: [run] } }, [], null);
    expect(reportText(failed)).toContain('请在摘要中补充可与正文实验结果对应的明确数值');
    expect(reportText(failed)).toContain('前置条件未全部通过');
  });
});

describe('paginated report layout', () => {
  const measure = (text: string) => Array.from(text).length * 10;
  it('wraps long CJK lines and preserves blank lines without clipping', () => {
    expect(wrapText('中文测试\n\n下一行', 20, measure)).toEqual(['中文', '测试', '', '下一', '行']);
  });
  it('includes all long-report text across bounded pages', () => {
    const text = '长篇内容'.repeat(1000);
    const pages = paginateReport([{ kind: 'text', text }], measure, {
      pageHeight: 300,
      pageWidth: 260,
      margin: 30,
      top: 40,
      bottom: 40,
    });
    expect(pages.length).toBeGreaterThan(5);
    expect(pages.flatMap((p) => p.lines.map((l) => l.text)).join('')).toBe(text);
    expect(pages.every((p) => p.lines.every((l) => l.y + l.lineHeight <= 260))).toBe(true);
  });
  it('gives an empty-findings report a complete, nonblank summary', () => {
    const model = buildExportReport(
      {
        ...fixture,
        result: { ...fixture.result, summary: { ...fixture.result.summary, finding_count: 0 }, rule_runs: [] },
      },
      [],
      null,
    );
    expect(reportBlocks(model).some((b) => b.text.includes('未发现问题'))).toBe(true);
  });
});

describe('English export word wrapping', () => {
  const measure = (text: string) => Array.from(text).length;
  it('keeps complete English words together and preserves every original space and punctuation', () => {
    const text = 'Verify that matching citations stay away from incorrect wrapping.';
    const lines = wrapText(text, 13, measure, 'word');
    expect(lines.join('')).toBe(text);
    expect(lines.every((line) => measure(line) <= 13)).toBe(true);
    for (const word of text.match(/[A-Za-z]+/g) || []) expect(lines.some((line) => line.includes(word))).toBe(true);
    expect(lines).not.toEqual(wrapText(text, 13, measure));
  });
  it('wraps mixed CJK/source quotes and overlong tokens safely without changing the text', () => {
    const text = '原文：matching 检测结果 abcdefghijklmnopqrstuvwxyz 中文校核。';
    const lines = wrapText(text, 10, measure, 'word');
    expect(lines.join('')).toBe(text);
    expect(lines.every((line) => measure(line) <= 10)).toBe(true);
    expect(lines.some((line) => line.includes('matching'))).toBe(true);
    expect(wrapText('中文测试\n\n下一行', 2, measure, 'word')).toEqual(['中文', '测试', '', '下一', '行']);
  });
  it('uses the English mode in pagination without changing the default Chinese path', () => {
    const text = 'Verify that matching citations stay away from incorrect wrapping.';
    const page = { pageHeight: 2000, pageWidth: 33, margin: 10, top: 20, bottom: 20 };
    const english = paginateReport([{ kind: 'text', text }], measure, page, 'word').flatMap((p) =>
      p.lines.map((l) => l.text),
    );
    expect(english.join('')).toBe(text);
    for (const word of text.match(/[A-Za-z]+/g) || []) expect(english.some((line) => line.includes(word))).toBe(true);
    const chinese = '中文测试原文不变'.repeat(3);
    expect(paginateReport([{ kind: 'quote', text: chinese }], measure, page)).toEqual(
      paginateReport([{ kind: 'quote', text: chinese }], measure, page, 'character'),
    );
  });
});
