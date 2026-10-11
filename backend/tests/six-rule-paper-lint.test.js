import { describe, expect, it, beforeEach, afterEach } from 'vitest';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const { getPaperLintCatalog, validateExternalProcessingConsent } =
  require('../src/normative/reviewPilotPaperLintService');
const { getSixRules, isSixRuleId, toSixRuleResult } =
  require('../src/normative/sixRulePaperLintService');

const box = { x1: 40, y1: 50, x2: 200, y2: 70, width: 595, height: 842, page_number: 2 };
const finding = {
  rule_id: '11', page: 2, message: '图 99 不存在',
  location: { type: 'pdf_bbox', page_number: 2, bounding_rect: box, rects: [box], text_excerpt: '图 99' },
};

describe('six PDF rules integration', () => {
  const previous = process.env.MINERU_API_TOKEN;
  afterEach(() => {
    if (previous === undefined) delete process.env.MINERU_API_TOKEN;
    else process.env.MINERU_API_TOKEN = previous;
  });
  beforeEach(() => { delete process.env.MINERU_API_TOKEN; });

  it('catalog preserves four old rules and exposes six new rules', async () => {
    const catalog = await getPaperLintCatalog({ refresh: true });
    for (const number of [11, 13, 14, 15, 16, 29, 18, 22, 24, 28]) {
      expect(catalog.rules.some((rule) => rule.rule_id === 'sjtu_rule_' + number)).toBe(true);
    }
    expect(catalog.rules.find((rule) => rule.rule_id === 'sjtu_rule_13').available).toBe(false);
    process.env.MINERU_API_TOKEN = 'test-secret';
    expect(getSixRules().find((rule) => rule.rule_id === 'sjtu_rule_13').available).toBe(true);
    expect(isSixRuleId('sjtu_rule_29')).toBe(true);
    expect(isSixRuleId('sjtu_rule_18')).toBe(false);
  });

  it('maps every finding and unsupported rule without dropping bounding boxes', () => {
    const result = toSixRuleResult({ pages: 5, rules: {
      11: { status: 'completed', findings: [finding, { ...finding, page: 3,
        location: { ...finding.location, page_number: 3,
          bounding_rect: { ...box, page_number: 3, y1: 100 }, rects: [{ ...box, page_number: 3, y1: 100 }] } }] },
      13: { status: 'unsupported', reason: 'MinerU 解析失败', findings: [] },
    } }, ['sjtu_rule_11', 'sjtu_rule_13']);
    expect(result.rule_runs[0].findings).toHaveLength(2);
    expect(result.rule_runs[0].findings[1].location.bounding_rect.y1).toBe(100);
    expect(result.rule_runs[1].outcome).toBe('inconclusive');
    expect(result.summary.finding_count).toBe(2);
  });

  it('reports one bilingual figure issue and keeps both caption rectangles', () => {
    const second = { ...box, y1: 75, y2: 95 };
    const location = { ...finding.location, bounding_rect: { ...box, y2: 95 },
      rects: [box, second], text_excerpt: '图 2.1 示例\nFigure 2.1 Example' };
    const result = toSixRuleResult({ rules: { 15: { status: 'completed', findings: [
      { rule_id: '15', message: '图 2.1 未被全文引用', location },
    ] } } }, ['sjtu_rule_15']);
    expect(result.summary.finding_count).toBe(1);
    expect(result.rule_runs[0].findings[0].location.rects).toEqual([box, second]);
  });

  it('MinerU selection needs no additional consent while DeepSeek still does', () => {
    process.env.MINERU_API_TOKEN = 'test-secret';
    const catalog = { rules: [
      ...getSixRules(),
      { rule_id: 'deepseek_rule', uses_external_model: true },
    ] };
    expect(() => validateExternalProcessingConsent(catalog, ['sjtu_rule_13'], false)).not.toThrow();
    expect(() => validateExternalProcessingConsent(catalog, ['deepseek_rule'], false)).toThrow();
  });
  it('allows OCR on a text rule to finish within the MinerU polling budget', async () => {
    const childProcess = require('node:child_process');
    const { promisify } = require('node:util');
    const filename = require.resolve('../src/normative/sixRulePaperLintService');
    const original = childProcess.execFile;
    let options;
    const fakeExec = () => { throw new Error('Expected promisified runner'); };
    fakeExec[promisify.custom] = async (_python, _args, settings) => {
      options = settings;
      return { stdout: JSON.stringify({ rules: { 11: { status: 'completed', findings: [] } } }) };
    };
    try {
      childProcess.execFile = fakeExec;
      delete require.cache[filename];
      const isolated = require(filename);
      const report = await isolated.runSixRules('scan.pdf', ['sjtu_rule_11']);
      expect(report.rule_runs[0].outcome).toBe('passed');
      expect(options.timeout).toBeGreaterThan(17 * 60 * 1000);
    } finally {
      childProcess.execFile = original;
      delete require.cache[filename];
    }
  });

});
