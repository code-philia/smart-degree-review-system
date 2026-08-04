import { describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { DEFAULT_NORMATIVE_RULES, analyzeDefaultNormativeRules } = require('../src/normative/normativeService');

const REQ_ID = 'FEAT-NORMATIVE-FORMAT-RULES';
void REQ_ID;

const requiredIssueFields = ['rule_id', 'category', 'severity', 'line', 'column', 'excerpt', 'message', 'suggestion'];

function expectIssueShape(issue) {
  for (const field of requiredIssueFields) {
    expect(issue, `missing ${field}`).toHaveProperty(field);
  }
  expect(typeof issue.rule_id).toBe('string');
  expect(typeof issue.category).toBe('string');
  expect(typeof issue.severity).toBe('string');
  expect(Number.isInteger(issue.line)).toBe(true);
  expect(Number.isInteger(issue.column)).toBe(true);
  expect(issue.line).toBeGreaterThanOrEqual(1);
  expect(issue.column).toBeGreaterThanOrEqual(1);
  expect(typeof issue.excerpt).toBe('string');
  expect(typeof issue.message).toBe('string');
  expect(typeof issue.suggestion).toBe('string');
}

function byCategory(issues, category) {
  return issues.filter((issue) => issue.category === category);
}

describe('FEAT-NORMATIVE-FORMAT-RULES default rule engine', () => {
  it('publishes the six built-in executable rule families', () => {
    expect(DEFAULT_NORMATIVE_RULES.map((rule) => rule.category)).toEqual([
      '章节顺序',
      '标点配对',
      '重复标点',
      '日期格式',
      '参考文献',
      '文本质量',
    ]);
  });

  it('detects the scenario pairing, repeated punctuation, and long sentence issues with line and column positions', async () => {
    const longSentence = `这是一个超过一百二十字符的句子${'内容'.repeat(70)}。`;
    const text = [
      '摘要',
      '关键词',
      '引言',
      `学生提交包含未配对（括号。。${longSentence}`,
      '结论',
      '参考文献',
      '[1] 示例文献',
    ].join('\n');

    const { issues } = await analyzeDefaultNormativeRules(text);

    const pairingIssue = byCategory(issues, '标点配对').find((issue) => issue.excerpt.includes('（'));
    const repeatedPunctuationIssue = byCategory(issues, '重复标点').find((issue) => issue.excerpt.includes('。。'));
    const longSentenceIssue = byCategory(issues, '文本质量').find((issue) => issue.message.includes('120'));

    expect(pairingIssue).toBeTruthy();
    expect(repeatedPunctuationIssue).toBeTruthy();
    expect(longSentenceIssue).toBeTruthy();
    [pairingIssue, repeatedPunctuationIssue, longSentenceIssue].forEach(expectIssueShape);
    expect(pairingIssue).toMatchObject({ rule_id: 'NORM-002', line: 4 });
    expect(repeatedPunctuationIssue).toMatchObject({ rule_id: 'NORM-003', line: 4 });
    expect(longSentenceIssue).toMatchObject({ rule_id: 'NORM-006', line: 4 });
  });

  it('detects missing or out-of-order required sections', async () => {
    const { issues } = await analyzeDefaultNormativeRules(['摘要', '引言', '关键词', '正文', '参考文献'].join('\n'));

    const sectionIssues = byCategory(issues, '章节顺序');
    expect(sectionIssues.length).toBeGreaterThan(0);
    expect(sectionIssues.some((issue) => issue.message.includes('结论') || issue.excerpt.includes('结论'))).toBe(true);
    sectionIssues.forEach(expectIssueShape);
  });

  it('detects unmatched Chinese and English punctuation pairs plus quote and book-title delimiters', async () => {
    const text = ['摘要', '关键词', '引言', '这一行包含(未闭合、[未闭合、《未闭合、“未闭合。', '结论', '参考文献', '[1] 示例文献'].join('\n');

    const { issues } = await analyzeDefaultNormativeRules(text);
    const pairingIssues = byCategory(issues, '标点配对');

    expect(pairingIssues.length).toBeGreaterThanOrEqual(4);
    expect(pairingIssues.map((issue) => issue.excerpt).join(' ')).toEqual(expect.stringContaining('('));
    expect(pairingIssues.map((issue) => issue.excerpt).join(' ')).toEqual(expect.stringContaining('['));
    expect(pairingIssues.map((issue) => issue.excerpt).join(' ')).toEqual(expect.stringContaining('《'));
    expect(pairingIssues.map((issue) => issue.excerpt).join(' ')).toEqual(expect.stringContaining('“'));
    pairingIssues.forEach(expectIssueShape);
  });

  it('detects configured repeated punctuation forms and runs of three or more identical punctuation marks', async () => {
    const text = ['摘要', '关键词', '引言', '这里有，，还有。。以及；；和!!!!!!', '结论', '参考文献', '[1] 示例文献'].join('\n');

    const { issues } = await analyzeDefaultNormativeRules(text);
    const repeatedIssues = byCategory(issues, '重复标点');

    expect(repeatedIssues.some((issue) => issue.excerpt.includes('，，'))).toBe(true);
    expect(repeatedIssues.some((issue) => issue.excerpt.includes('。。'))).toBe(true);
    expect(repeatedIssues.some((issue) => issue.excerpt.includes('；；'))).toBe(true);
    expect(repeatedIssues.some((issue) => issue.excerpt.includes('!!!'))).toBe(true);
    repeatedIssues.forEach(expectIssueShape);
  });

  it('accepts only YYYY-MM-DD numeric dates and reports other numeric date formats', async () => {
    const text = ['摘要', '关键词', '引言', '正确日期 2026-08-03 不应报错，错误日期 2026/08/03 和 2026-8-3 应报错。', '结论', '参考文献', '[1] 示例文献'].join('\n');

    const { issues } = await analyzeDefaultNormativeRules(text);
    const dateIssues = byCategory(issues, '日期格式');

    expect(dateIssues.some((issue) => issue.excerpt.includes('2026/08/03'))).toBe(true);
    expect(dateIssues.some((issue) => issue.excerpt.includes('2026-8-3'))).toBe(true);
    expect(dateIssues.some((issue) => issue.excerpt.includes('2026-08-03'))).toBe(false);
    dateIssues.forEach(expectIssueShape);
  });

  it('requires reference lines after 参考文献 to start at [1] and increment continuously', async () => {
    const text = ['摘要', '关键词', '引言', '正文。', '结论', '参考文献', '[2] 第一条不应从二开始', '[4] 第二条不连续'].join('\n');

    const { issues } = await analyzeDefaultNormativeRules(text);
    const referenceIssues = byCategory(issues, '参考文献');

    expect(referenceIssues.length).toBeGreaterThanOrEqual(2);
    expect(referenceIssues[0]).toMatchObject({ rule_id: 'NORM-005', line: 7, column: 1 });
    referenceIssues.forEach(expectIssueShape);
  });

  it('detects text quality problems including repeated words, tabs, trailing spaces, long sentences, and disabled words', async () => {
    const longSentence = `这是一个超过一百二十字符的句子${'质量'.repeat(70)}。`;
    const text = ['摘要', '关键词', '引言', `这个 这个 词连续重复，包含\t制表符，且行尾有空格。   `, `显然需要避免禁用词。${longSentence}`, '结论', '参考文献', '[1] 示例文献'].join('\n');

    const { issues } = await analyzeDefaultNormativeRules(text);
    const qualityIssues = byCategory(issues, '文本质量');

    expect(qualityIssues.some((issue) => issue.message.includes('连续重复词') || issue.excerpt.includes('这个 这个'))).toBe(true);
    expect(qualityIssues.some((issue) => issue.message.includes('Tab') || issue.message.includes('制表符'))).toBe(true);
    expect(qualityIssues.some((issue) => issue.message.includes('行尾空格'))).toBe(true);
    expect(qualityIssues.some((issue) => issue.message.includes('120'))).toBe(true);
    expect(qualityIssues.some((issue) => issue.message.includes('禁用词') || issue.excerpt.includes('显然'))).toBe(true);
    qualityIssues.forEach(expectIssueShape);
  });

  it('rejects non-string input at the service boundary', async () => {
    await expect(analyzeDefaultNormativeRules(null)).rejects.toMatchObject({ code: 'NORMATIVE_RULES_INVALID_INPUT' });
  });
});
