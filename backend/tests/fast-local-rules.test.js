import { createRequire } from 'node:module';
import { describe, it, expect } from 'vitest';
const require = createRequire(import.meta.url);
const registry = require('../rules/registry');
const service = require('../src/normative/reviewPilotPaperLintService');
const compiler = require('../src/normative/paperCompilerService');

describe('three local rules', () => {
  it('publishes ten native rules and keeps the six new titles unnumbered', async () => {
    const { rules } = await service.getPaperLintCatalog({ mvpOnly: true });
    expect(rules).toHaveLength(10);
    for (const id of ['sjtu_rule_31', 'required_section_completeness_check', 'chinese_english_symbol_mix_check', 'keyword_count_check', 'abstract_object_number_check', 'chapter_new_page_check']) {
      expect(rules.find(rule => rule.rule_id === id)).toMatchObject({ enabled_in_mvp: true, uses_external_model: false });
      expect(registry.getRuleDefinition(id).title).not.toMatch(/规则\s*\d/);
    }
    expect(compiler.isCompilerRuleId('sjtu_rule_31')).toBe(false);
  });
});
