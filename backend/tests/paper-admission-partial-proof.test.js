import { createRequire } from 'node:module';
import crypto from 'node:crypto';
import { afterAll, expect, it } from 'vitest';

const require = createRequire(import.meta.url);
const boundary = require('../src/normative/paperLintProcess');
const originalProcess = boundary.runPaperLintProcess;
let payload;
boundary.runPaperLintProcess = async () => ({ stdout: JSON.stringify(payload) });
const modulePath = require.resolve('../src/normative/paperDocumentAdmission');
delete require.cache[modulePath];
const { assessPaperDocument, unavailableReferenceRuleIds } = require(modulePath);
afterAll(() => { boundary.runPaperLintProcess = originalProcess; delete require.cache[modulePath]; });

const buffer = Buffer.from('%PDF-test-proof');
const required = ['摘要', '英文摘要', '关键词', '目录', '引言', '主体', '结论', '参考文献'];
function proof(missing = [], incomplete = []) {
  const partial = missing.length + incomplete.length > 0;
  return { version: 'paper-admission/2.0', status: 'accepted', compiled: true,
    reason: partial ? '缺失或不完整的章节。' : '已识别完整论文。',
    reason_code: partial ? 'paper_structure_incomplete' : 'paper_structure_confirmed',
    stage: partial ? 'partial' : 'complete',
    sha256: crypto.createHash('sha256').update(buffer).digest('hex'),
    structure: { status: partial ? 'rejected' : 'accepted', profile: 'chinese-thesis',
      required_sections: [...required], missing_sections: missing, incomplete_sections: incomplete,
      observed_sections: Object.fromEntries(required.map(name => [name, !missing.includes(name)])) } };
}

it.each([
  [[], []], [['参考文献'], []], [['英文摘要'], []], [[], ['英文摘要']],
])('accepts a consistent compiled complete/partial proof (%j, %j)', async (missing, incomplete) => {
  payload = proof(missing, incomplete);
  expect(await assessPaperDocument('unused.pdf', buffer)).toEqual(payload);
});

it.each([
  p => { p.compiled = false; },
  p => { p.sha256 = '0'.repeat(64); },
  p => { p.reason_code = 'non_paper_identity'; },
  p => { p.structure.observed_sections['参考文献'] = true; },
  p => { p.structure.missing_sections = ['不存在的章节']; },
  p => { p.structure.incomplete_sections = ['参考文献']; },
  p => { delete p.structure.incomplete_sections; },
  p => { p.structure.required_sections[0] = '参考文献'; },
])('fails closed for contradictory or malformed partial proof %#', async mutate => {
  payload = proof(['参考文献']); mutate(payload);
  expect(await assessPaperDocument('unused.pdf', buffer)).toMatchObject({
    status: 'rejected', reason_code: 'validation_unavailable',
  });
});

it('only blocks bibliography-dependent rules when bibliography is actually missing', () => {
  const ids = ['sjtu_rule_18', 'sjtu_rule_22', 'sjtu_rule_24', 'sjtu_rule_31',
    'sjtu_rule_32', 'sjtu_rule_33', 'required_section_completeness_check'];
  expect(unavailableReferenceRuleIds(proof(['参考文献']), ids)).toEqual([
    'sjtu_rule_24', 'sjtu_rule_31', 'sjtu_rule_32', 'sjtu_rule_33',
  ]);
  expect(unavailableReferenceRuleIds(proof(['英文摘要']), ids)).toEqual([]);
  expect(unavailableReferenceRuleIds(proof([], ['英文摘要']), ids)).toEqual([]);
  expect(unavailableReferenceRuleIds(proof(), ids)).toEqual([]);
});
