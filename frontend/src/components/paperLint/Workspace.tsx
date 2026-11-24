import { useCallback, useState } from 'react';
import type { PaperLintFinding, PaperLintRule, PaperLintRuleRun } from '../../api/paperLint';
import type { RepairSuggestion } from '../../api/repairSuggestions';
import type { FindingFeedback, SuggestionFeedback } from '../../api/feedback';
import { FindingsPane } from './FindingsPane';
import { genericExecutionWarnings, numericExecutionWarnings } from './model';
import type { PaperLintFindingItem } from './model';
import { PdfPane } from './PdfPane';
import type { PdfPageLabels } from './pageLabels';
import { referenceVerificationSummary } from './ReferenceVerificationDetails';

function referencePdfFindingKey(run: PaperLintRuleRun, index: number) {
  return `reference-verified:${run.rule_run_id}:${index}`;
}

function referencePdfFindings(runs: PaperLintRuleRun[]): PaperLintFindingItem[] {
  return runs.flatMap(run => {
    if (run.rule_id !== 'reference_verification_check') return [];
    const summary = referenceVerificationSummary(run.params?.reference_verification);
    return (summary?.entries || []).flatMap((check, index) => {
      if (check.category !== 'verified' || !check.entry.location) return [];
      const key = referencePdfFindingKey(run, index);
      // Display-only navigation targets. These never enter report findings,
      // issue counts, feedback, exports or persisted results.
      return [{ key, index, ruleRun: run, finding: {
        finding_id: key, rule_id: run.rule_id,
        message: check.entry.text || check.entry.title || '',
        location: check.entry.location, reference_check: check, source_kind: 'source',
        anchors: [{ anchor_id: 'verified-reference', role: 'source', label: '已核验 / Verified', location: check.entry.location }],
      } }];
    });
  });
}

function numericPdfFindings(run: PaperLintRuleRun | undefined): PaperLintFindingItem[] {
  if (!run || run.rule_id !== 'abstract_numeric_consistency_check') return [];
  const rows = Array.isArray(run.params?.numeric_results)
    ? run.params.numeric_results.filter((row): row is Record<string, unknown> => Boolean(row && typeof row === 'object'))
    : [];
  return rows.flatMap((row, index) => {
    const declarationId = String(row.declaration_id || index);
    const anchors = [row.abstract_anchors, row.evidence_anchors]
      .flatMap((value) => Array.isArray(value) ? value : [])
      .filter((anchor): anchor is Record<string, unknown> => Boolean(anchor && typeof anchor === 'object' && anchor.location));
    if (!anchors.length) return [];
    const findingId = `${run.rule_id}_${declarationId}`;
    const finding: PaperLintFinding = {
      finding_id: findingId,
      rule_id: run.rule_id,
      message: String(row.reason || '数值论点原文证据'),
      location: (anchors[0].location || null) as PaperLintFinding['location'],
      anchors: anchors as PaperLintFinding['anchors'],
    };
    return [{ key: findingId, finding, ruleRun: run, index }];
  });
}

type Props = {
  file: File | { name: string; url: string };
  layout?: 'default' | 'semantic';
  findings: PaperLintFindingItem[];
  rules: PaperLintRule[];
  selectedRuleIds?: string[];
  ruleRuns?: PaperLintRuleRun[];
  openPdfUrl?: string;
  numericReviewRun?: PaperLintRuleRun;
  running?: boolean;
  readOnly?: boolean;
  repairSuggestionByFindingKey?: Record<string, RepairSuggestion | undefined>;
  repairSuggestionLoadingKey?: string | null;
  repairSuggestionLoadingByFindingKey?: Record<string, boolean>;
  repairSuggestionErrorByFindingKey?: Record<string, string | undefined>;
  onLoadRepairSuggestion?: (finding: PaperLintFindingItem) => void;
  onGenerateRepairSuggestion?: (finding: PaperLintFindingItem) => void;
  supportsRepairSuggestion?: (finding: PaperLintFindingItem) => boolean;
  forceNewRepairSuggestion?: boolean;
  findingFeedbackByKey?: Record<string, FindingFeedback | null | undefined>;
  suggestionFeedbackByFindingKey?: Record<string, SuggestionFeedback | null | undefined>;
  onFindingFeedback?: (finding: PaperLintFindingItem, value: 'positive' | 'negative') => void;
  onFindingFeedbackReason?: (finding: PaperLintFindingItem, reasonCode: string | null, reasonText: string | null) => void | Promise<void>;
  onFindingFeedbackCancel?: (finding: PaperLintFindingItem) => void;
  onSuggestionFeedback?: (finding: PaperLintFindingItem, value: 'positive' | 'negative') => void;
  onSuggestionFeedbackReason?: (finding: PaperLintFindingItem, reasonCode: string | null, reasonText: string | null) => void | Promise<void>;
  onSuggestionFeedbackCancel?: (finding: PaperLintFindingItem) => void;
};

export function PaperLintWorkspace({
  file,
  layout = 'default',
  findings,
  rules,
  selectedRuleIds,
  ruleRuns,
  openPdfUrl,
  numericReviewRun,
  running = false,
  readOnly = false,
  repairSuggestionByFindingKey = {},
  repairSuggestionLoadingKey = null,
  repairSuggestionLoadingByFindingKey = {},
  repairSuggestionErrorByFindingKey = {},
  onLoadRepairSuggestion,
  onGenerateRepairSuggestion,
  supportsRepairSuggestion,
  forceNewRepairSuggestion,
  findingFeedbackByKey,
  suggestionFeedbackByFindingKey,
  onFindingFeedback,
  onFindingFeedbackReason,
  onFindingFeedbackCancel,
  onSuggestionFeedback,
  onSuggestionFeedbackReason,
  onSuggestionFeedbackCancel,
}: Props) {
  const [pageLabels, setPageLabels] = useState<PdfPageLabels>({});
  const pdfFindings = (() => {
    const byKey = new Map(findings.map((item) => [item.key, item]));
    for (const item of [...numericPdfFindings(numericReviewRun), ...referencePdfFindings(ruleRuns || [])]) {
      if (!byKey.has(item.key)) byKey.set(item.key, item);
    }
    return Array.from(byKey.values());
  })();
  const [activeFindingKey, setActiveFindingKey] = useState<string | null>(findings[0]?.key || null);
  const [activeAnchorId, setActiveAnchorId] = useState<string | null>(null);
  const [navigationRequest, setNavigationRequest] = useState(0);
  const selectFinding = useCallback((key: string) => {
    setActiveFindingKey(key);
    setActiveAnchorId(null);
    setRequestedPage(null);
    setNavigationRequest((current) => current + 1);
  }, [])
  const [requestedPage, setRequestedPage] = useState<number | null>(null);
  const selectAnchor = useCallback((key: string, anchorId: string) => {
    setActiveFindingKey(key);
    setActiveAnchorId(anchorId);
    setRequestedPage(null);
    setNavigationRequest((current) => current + 1);
  }, []);

  return (
    <div className={`grid gap-4 [--pdf-preview-min-height:0px] [--report-height:clamp(420px,calc(100dvh-10rem),960px)] [&>section]:h-[var(--report-height)] lg:h-[var(--report-height)] lg:[&>section]:h-auto ${layout === 'semantic' ? 'lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]' : 'lg:grid-cols-[minmax(0,1.25fr)_minmax(340px,.75fr)]'}`}>
      <PdfPane
        file={file}
        openPdfUrl={openPdfUrl}
        findings={pdfFindings}
        activeFindingKey={activeFindingKey}
        activeAnchorId={activeAnchorId}
        navigationRequest={navigationRequest}
        requestedPage={requestedPage}
        onFindingClick={selectFinding}
        onAnchorClick={selectAnchor}
        onPageLabels={setPageLabels}
      />
      <div className="flex min-h-0 max-h-[var(--report-height)] flex-col gap-3 [&>section]:flex-1">
      <FindingsPane
        readOnly={readOnly}
        executionWarnings={[
          ...numericExecutionWarnings(numericReviewRun),
          ...genericExecutionWarnings(ruleRuns || []),
        ]}
        pageLabels={pageLabels}
        findings={findings}
        selectedRuleIds={selectedRuleIds}
        ruleRuns={ruleRuns}
        running={running}
        rules={rules}
        activeFindingKey={activeFindingKey}
        activeAnchorId={activeAnchorId}
        onFindingClick={selectFinding}
        onAnchorClick={selectAnchor}
        onReferenceEntryClick={(run, _check, index) => selectFinding(referencePdfFindingKey(run, index))}
        repairSuggestionByFindingKey={repairSuggestionByFindingKey}
        repairSuggestionLoadingKey={repairSuggestionLoadingKey}
        repairSuggestionLoadingByFindingKey={repairSuggestionLoadingByFindingKey}
        repairSuggestionErrorByFindingKey={repairSuggestionErrorByFindingKey}
        onLoadRepairSuggestion={onLoadRepairSuggestion}
        onGenerateRepairSuggestion={onGenerateRepairSuggestion}
        supportsRepairSuggestion={supportsRepairSuggestion}
        forceNewRepairSuggestion={forceNewRepairSuggestion}
        findingFeedbackByKey={findingFeedbackByKey}
        suggestionFeedbackByFindingKey={suggestionFeedbackByFindingKey}
        onFindingFeedback={onFindingFeedback}
        onFindingFeedbackReason={onFindingFeedbackReason}
        onFindingFeedbackCancel={onFindingFeedbackCancel}
        onSuggestionFeedback={onSuggestionFeedback}
        onSuggestionFeedbackReason={onSuggestionFeedbackReason}
        onSuggestionFeedbackCancel={onSuggestionFeedbackCancel}
      />
      </div>
    </div>
  );
}
