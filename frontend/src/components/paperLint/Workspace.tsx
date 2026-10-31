import { useCallback, useState } from 'react';
import type { PaperLintFinding, PaperLintRule, PaperLintRuleRun } from '../../api/paperLint';
import type { RepairSuggestion } from '../../api/repairSuggestions';
import type { FindingFeedback, SuggestionFeedback } from '../../api/feedback';
import { FindingsPane } from './FindingsPane';
import { NumericReviewDetails } from './NumericReviewDetails';
import type { PaperLintFindingItem } from './model';
import { PdfPane } from './PdfPane';

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
  openPdfUrl?: string;
  numericReviewRun?: PaperLintRuleRun;
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
  onFindingFeedbackReason?: (finding: PaperLintFindingItem, reasonCode: string | null, reasonText: string | null) => void;
  onFindingFeedbackCancel?: (finding: PaperLintFindingItem) => void;
  onSuggestionFeedback?: (finding: PaperLintFindingItem, value: 'positive' | 'negative') => void;
  onSuggestionFeedbackReason?: (finding: PaperLintFindingItem, reasonCode: string | null, reasonText: string | null) => void;
  onSuggestionFeedbackCancel?: (finding: PaperLintFindingItem) => void;
};

export function PaperLintWorkspace({
  file,
  layout = 'default',
  findings,
  rules,
  openPdfUrl,
  numericReviewRun,
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
  const pdfFindings = (() => {
    if (layout !== 'semantic' || !numericReviewRun) return findings;
    const byKey = new Map(findings.map((item) => [item.key, item]));
    for (const item of numericPdfFindings(numericReviewRun)) if (!byKey.has(item.key)) byKey.set(item.key, item);
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
  const selectPage = useCallback((page: number) => {
    setActiveFindingKey(null);
    setActiveAnchorId(null);
    setNavigationRequest((current) => current + 1);
    setRequestedPage(page);
  }, []);
  const [requestedPage, setRequestedPage] = useState<number | null>(null);
  const selectAnchor = useCallback((key: string, anchorId: string) => {
    setActiveFindingKey(key);
    setActiveAnchorId(anchorId);
    setRequestedPage(null);
    setNavigationRequest((current) => current + 1);
  }, []);

  return (
    <div className={`grid min-h-[620px] gap-4 lg:h-[min(78vh,860px)] ${layout === 'semantic' ? 'lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]' : 'lg:grid-cols-[minmax(0,1.25fr)_minmax(340px,.75fr)]'}`}>
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
      />
      {layout === 'semantic' && numericReviewRun ? (
        <section className="min-h-0 overflow-y-auto rounded-xl border border-slate-200 bg-white p-4">
          <NumericReviewDetails
            run={numericReviewRun}
            findings={pdfFindings}
            onAnchorClick={selectAnchor}
            onPageClick={selectPage}
          />
        </section>
      ) : <FindingsPane
        findings={findings}
        rules={rules}
        activeFindingKey={activeFindingKey}
        activeAnchorId={activeAnchorId}
        onFindingClick={selectFinding}
        onAnchorClick={selectAnchor}
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
      />}
    </div>
  );
}
