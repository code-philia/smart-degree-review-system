import { describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const registry = require('../rules/registry');

describe('rule registry', () => {
  it('declares eight native MVP rules and preserves existing repair capabilities', () => {
    expect(registry.getEnabledMvpRuleIds()).toEqual([
      'sjtu_rule_18', 'sjtu_rule_22', 'sjtu_rule_24', 'sjtu_rule_28', 'sjtu_rule_31',
      'required_section_completeness_check', 'chinese_english_symbol_mix_check',
      'keyword_count_check',
    ]);
    for (const ruleId of registry.getEnabledMvpRuleIds()) {
      expect(registry.getRuleDefinition(ruleId)).toMatchObject({
        family: 'local_pdf',
        enabled_in_mvp: true,
      });
      expect(registry.getRuleDefinition(ruleId).uses_external_model).toBe(false);
    }
  });

  it('keeps non-MVP legacy families registered without exposing them as MVP rules', () => {
    expect(registry.listRuleDefinitions({ family: 'six_pdf' }).map((rule) => rule.rule_id)).toEqual([
      'sjtu_rule_11', 'sjtu_rule_13', 'sjtu_rule_14', 'sjtu_rule_15', 'sjtu_rule_16', 'sjtu_rule_29',
    ]);
    expect(registry.listRuleDefinitions({ family: 'compiler' }).map((rule) => rule.rule_id)).toEqual([
      'sjtu_rule_32', 'sjtu_rule_33',
    ]);
    expect(registry.getEnabledMvpRuleIds()).not.toContain('sjtu_rule_15');
    expect(registry.supportsRepairSurface('sjtu_rule_18', 'paper_lint')).toBe(true);
    expect(registry.supportsRepairSurface('sjtu_rule_15', 'paper_lint')).toBe(false);
    expect(registry.supportsRepairSurface('sjtu_rule_15', 'archive')).toBe(true);
  });
});
