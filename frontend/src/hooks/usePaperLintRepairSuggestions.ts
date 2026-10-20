import { useCallback, useEffect, useRef, useState } from 'react';
import {
  evaluatePaperLintFindingRepairSuggestion,
  fetchPaperLintFindingRepairSuggestion,
  PAPER_LINT_REPAIR_RULE_IDS,
  type RepairSuggestion,
} from '../api/repairSuggestions';
import type { PaperLintFindingItem } from '../components/paperLint/model';

function messageOf(cause: unknown) {
  return cause instanceof Error && cause.message ? cause.message : '修复建议暂不可用';
}

export function usePaperLintRepairSuggestions(reportId: string | undefined) {
  const [repairSuggestionByFindingKey, setRepairSuggestionByFindingKey] = useState<
    Record<string, RepairSuggestion | undefined>
  >({});
  const [repairSuggestionErrorByFindingKey, setRepairSuggestionErrorByFindingKey] = useState<
    Record<string, string | undefined>
  >({});
  const [repairSuggestionLoadingKey, setRepairSuggestionLoadingKey] = useState<string | null>(null);
  const loadedKeys = useRef(new Set<string>());

  useEffect(() => {
    loadedKeys.current = new Set();
    setRepairSuggestionByFindingKey({});
    setRepairSuggestionErrorByFindingKey({});
    setRepairSuggestionLoadingKey(null);
  }, [reportId]);

  const supportsRepairSuggestion = useCallback(
    (item: PaperLintFindingItem) => PAPER_LINT_REPAIR_RULE_IDS.has(item.ruleRun.rule_id),
    [],
  );

  const loadRepairSuggestion = useCallback(async (item: PaperLintFindingItem) => {
    if (!reportId || !supportsRepairSuggestion(item) || loadedKeys.current.has(item.key)) return;
    loadedKeys.current.add(item.key);
    setRepairSuggestionLoadingKey(item.key);
    setRepairSuggestionErrorByFindingKey((current) => ({ ...current, [item.key]: undefined }));
    try {
      const response = await fetchPaperLintFindingRepairSuggestion({
        report_id: reportId,
        rule_id: item.ruleRun.rule_id,
        finding_id: item.finding.finding_id,
      });
      if (response) setRepairSuggestionByFindingKey((current) => ({ ...current, [item.key]: response }));
    } catch (cause) {
      setRepairSuggestionErrorByFindingKey((current) => ({ ...current, [item.key]: messageOf(cause) }));
    } finally {
      setRepairSuggestionLoadingKey((current) => (current === item.key ? null : current));
    }
  }, [reportId, supportsRepairSuggestion]);

  const generateRepairSuggestion = useCallback(async (item: PaperLintFindingItem) => {
    if (!reportId || !supportsRepairSuggestion(item)) return;
    setRepairSuggestionLoadingKey(item.key);
    setRepairSuggestionErrorByFindingKey((current) => ({ ...current, [item.key]: undefined }));
    try {
      const { response } = await evaluatePaperLintFindingRepairSuggestion({
        report_id: reportId,
        rule_id: item.ruleRun.rule_id,
        finding_id: item.finding.finding_id,
      }, { force: true });
      setRepairSuggestionByFindingKey((current) => ({ ...current, [item.key]: response }));
      loadedKeys.current.add(item.key);
    } catch (cause) {
      setRepairSuggestionErrorByFindingKey((current) => ({ ...current, [item.key]: messageOf(cause) }));
    } finally {
      setRepairSuggestionLoadingKey((current) => (current === item.key ? null : current));
    }
  }, [reportId, supportsRepairSuggestion]);

  return {
    repairSuggestionByFindingKey,
    repairSuggestionErrorByFindingKey,
    repairSuggestionLoadingKey,
    supportsRepairSuggestion,
    loadRepairSuggestion,
    generateRepairSuggestion,
  };
}
