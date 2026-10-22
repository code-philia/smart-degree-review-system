import { useCallback } from 'react';
import { evaluatePaperLintFindingRepairSuggestion, fetchPaperLintFindingRepairSuggestion, PAPER_LINT_REPAIR_RULE_IDS } from '../api/repairSuggestions';
import type { PaperLintFindingItem } from '../components/paperLint/model';
import { useFindingRepairSuggestions } from './useFindingRepairSuggestions';
export function usePaperLintRepairSuggestions(reportId: string | undefined) {
  const reference = useCallback((item: PaperLintFindingItem) => ({report_id: reportId!, rule_id: item.ruleRun.rule_id, finding_id: item.finding.finding_id}), [reportId]);
  const fetchSaved = useCallback((item: PaperLintFindingItem) => fetchPaperLintFindingRepairSuggestion(reference(item)), [reference]);
  const evaluate = useCallback((item: PaperLintFindingItem, force: boolean) => evaluatePaperLintFindingRepairSuggestion(reference(item), {force}), [reference]);
  return useFindingRepairSuggestions({scopeKey: reportId, fetchSaved, evaluate, supportedRuleIds: PAPER_LINT_REPAIR_RULE_IDS});
}
