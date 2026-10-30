import { describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const registry = require('../rules/registry');

describe('rule registry', () => {
  it('declares native, bilingual, and typo MVP rules and preserves repair capabilities', () => {
    expect(registry.getEnabledMvpRuleIds()).toEqual([
      'sjtu_rule_18', 'sjtu_rule_22', 'sjtu_rule_24', 'sjtu_rule_28', 'sjtu_rule_31', 'sjtu_rule_32', 'typo_detection_check',
      'bilingual_keywords_correspondence_check', 'bilingual_abstract_consistency_check',
      'required_section_completeness_check', 'chinese_english_symbol_mix_check',
      'keyword_count_check', 'abstract_object_number_check', 'chapter_new_page_check',
      'abstract_numeric_consistency_check',
    ]);
    for (const ruleId of registry.listRuleDefinitions({ family: 'local_pdf', enabledInMvp: true }).map(rule => rule.rule_id)) {
      expect(registry.getRuleDefinition(ruleId)).toMatchObject({
        family: 'local_pdf',
        enabled_in_mvp: true,
      });
      expect(registry.getRuleDefinition(ruleId).uses_external_model).toBe(false);
    }
  });

  it('keeps the existing bilingual semantic rules enabled in the MVP set', () => {
    expect(registry.listRuleDefinitions({ family: 'legacy_bridge' }).map((rule) => rule.rule_id)).toContain('bilingual_keywords_correspondence_check');
    expect(registry.listRuleDefinitions({ family: 'legacy_bridge' }).map((rule) => rule.rule_id)).toContain('bilingual_abstract_consistency_check');
    expect(registry.listRuleDefinitions({ family: 'legacy_bridge' }).map((rule) => rule.rule_id)).toContain('typo_detection_check');
    for (const ruleId of ['bilingual_keywords_correspondence_check', 'bilingual_abstract_consistency_check', 'typo_detection_check']) {
      expect(registry.getRuleDefinition(ruleId)).toMatchObject({
        execution_mode: 'semantic', uses_external_model: true,
        enabled_in_mvp: true, availability_probe: 'deepseek_api',
      });
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
