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

  it('MinerU selection needs no additional consent while DeepSeek still does', () => {
    process.env.MINERU_API_TOKEN = 'test-secret';
    const catalog = { rules: [
      ...getSixRules(),
      { rule_id: 'deepseek_rule', uses_external_model: true },
    ] };
    expect(() => validateExternalProcessingConsent(catalog, ['sjtu_rule_13'], false)).not.toThrow();
    expect(() => validateExternalProcessingConsent(catalog, ['deepseek_rule'], false)).toThrow();
  });
});
