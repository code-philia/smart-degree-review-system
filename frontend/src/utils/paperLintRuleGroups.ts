// The thirty-rules page currently exposes the enabled PDF MVP rules,
// including the two bilingual semantic rules. Keep this shared set in sync
// with the backend MVP registry so saved reports are not filtered out of history.
export const THIRTY_RULE_IDS = new Set([
  'abstract_numeric_consistency_check',
  'sjtu_rule_18',
  'sjtu_rule_22',
  'sjtu_rule_24',
  'sjtu_rule_28',
  'sjtu_rule_31',
  'required_section_completeness_check',
  'chinese_english_symbol_mix_check',
  'keyword_count_check',
  'abstract_object_number_check',
  'chapter_new_page_check',
  'bilingual_keywords_correspondence_check',
  'bilingual_abstract_consistency_check',
  'typo_detection_check',
  'required_section_completeness_check',
  'chinese_english_symbol_mix_check',
]);
