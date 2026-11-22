import { afterEach, expect, it } from 'vitest';
import { setLocale, translate, hasTranslation } from '../src/i18n/locale';
import registry from '../../backend/rules/registry.json';

const description = '按国标和学校规范检查论文必备组成部分，兼容空格与拆字标题。';
afterEach(() => setLocale('zh'));
it('publishes the requested core-section description in the live catalog', () => {
  const rules = Array.isArray(registry) ? registry : (registry as any).rules;
  expect(rules.find((r: any) => r.rule_id === 'required_section_completeness_check').description).toBe(description);
});
it('translates national and university scope and heading compatibility', () => {
  setLocale('en');
  expect(translate(description)).toBe('Check the required thesis sections against national and university standards, allowing for spaced and split-character headings.');
});
it('translates the new missing-section finding and school-specific advice', () => {
  setLocale('en');
  const message = '缺少学术论文和科研成果目录：未在论文正文中识别到该章节。';
  const suggestion = '请补齐或核对学术论文和科研成果目录；依据学校学位论文模板规范。';
  expect(hasTranslation(message, 'en')).toBe(true);
  expect(translate(message)).toBe('The list of academic publications and research achievements is missing: no matching section was identified in the thesis text.');
  expect(translate(suggestion)).toBe('Add or check the list of academic publications and research achievements, following the university thesis template requirements.');
});
