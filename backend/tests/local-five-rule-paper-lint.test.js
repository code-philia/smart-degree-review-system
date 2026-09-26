import { describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const { toPaperLintResult } = require('../src/normative/localFiveRulePaperLintService');

const rect = (page, y) => ({ x1: 80, y1: y, x2: 300, y2: y + 14, width: 595, height: 842, page_number: page });
const finding = (rule, page, y, token) => ({
  rule_id: String(rule), page, token, message: `引用 ${token} 未找到目标`,
  text_excerpt: `正文引用 [${token}]`,
  location: { type: 'pdf_bbox', page_number: page, bounding_rect: rect(page, y),
    rects: [rect(page, y)], text_excerpt: `正文引用 [${token}]` },
});

describe('local four-rule report adapter', () => {
  it('keeps every finding and its PDF bbox while exposing unsupported separately', () => {
    const result = toPaperLintResult({ pages: 8, rules: {
      22: { status: 'completed', findings: [finding(22, 2, 120, '99'), finding(22, 5, 310, '98')] },
      24: { status: 'completed', findings: [finding(24, 8, 510, '12')] },
      28: { status: 'unsupported', reason: '目录标题无法匹配', findings: [] },
    } }, ['sjtu_rule_22', 'sjtu_rule_24', 'sjtu_rule_28']);
    expect(result.rule_runs.map((run) => [run.rule_id, run.execution_status, run.outcome])).toEqual([
      ['sjtu_rule_22', 'completed', 'issues_found'],
      ['sjtu_rule_24', 'completed', 'issues_found'],
      ['sjtu_rule_28', 'unsupported', 'inconclusive'],
    ]);
    expect(result.rule_runs[0].findings).toHaveLength(2);
    expect(result.rule_runs[0].findings[1].location.bounding_rect).toEqual(rect(5, 310));
    expect(result.rule_runs[1].findings[0].location.page_number).toBe(8);
    expect(result.rule_runs[2].message).toContain('目录标题无法匹配');
    expect(result.summary).toMatchObject({ rule_count: 3, completed_rule_count: 2,
      unsupported_rule_count: 1, issue_rule_count: 2, finding_count: 3, warning_finding_count: 3 });
  });

  it('does not call an unsupported check a pass and rejects incomplete engine output', () => {
    const result = toPaperLintResult({ pages: 1, rules: {
      18: { status: 'completed', findings: [] },
      22: { status: 'unsupported', reason: '缺少参考文献表', findings: [] },
    } }, ['sjtu_rule_18', 'sjtu_rule_22']);
    expect(result.rule_runs.map((run) => run.outcome)).toEqual(['passed', 'inconclusive']);
    expect(result.summary.finding_count).toBe(0);
    try {
      toPaperLintResult({ rules: {} }, ['sjtu_rule_24']);
      throw new Error('Expected malformed detector output to fail');
    } catch (error) {
      expect(error.message).toMatch(/24/);
      expect(error.status).toBe(502);
    }
  });
});