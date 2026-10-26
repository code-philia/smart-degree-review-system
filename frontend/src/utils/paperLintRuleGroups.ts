// The thirty-rules page currently exposes the enabled PDF MVP rules,
// including the two bilingual semantic rules. Keep this shared set in sync
// with the backend MVP registry so saved reports are not filtered out of history.
export const THIRTY_RULE_IDS = new Set([
  'sjtu_rule_18',
  'sjtu_rule_22',
  'sjtu_rule_24',
  'sjtu_rule_28',
  'sjtu_rule_31',
  'bilingual_keywords_correspondence_check',
  'bilingual_abstract_consistency_check',
  'required_section_completeness_check',
  'chinese_english_symbol_mix_check',
]);
