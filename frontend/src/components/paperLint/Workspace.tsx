import { useCallback, useState } from 'react';
import type { PaperLintRule } from '../../api/paperLint';
import type { RepairSuggestion } from '../../api/repairSuggestions';
import type { FindingFeedback, SuggestionFeedback } from '../../api/feedback';
import { FindingsPane } from './FindingsPane';
import type { PaperLintFindingItem } from './model';
import { PdfPane } from './PdfPane';

type Props = {
  file: File | { name: string; url: string };
  layout?: 'default' | 'semantic';
  findings: PaperLintFindingItem[];
  rules: PaperLintRule[];
  openPdfUrl?: string;
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
  const [activeFindingKey, setActiveFindingKey] = useState<string | null>(findings[0]?.key || null);
  const [activeAnchorId, setActiveAnchorId] = useState<string | null>(null);
  const [navigationRequest, setNavigationRequest] = useState(0);
  const selectFinding = useCallback((key: string) => {
    setActiveFindingKey(key);
    setActiveAnchorId(null);
    setNavigationRequest((current) => current + 1);
  }, []);
  const selectAnchor = useCallback((key: string, anchorId: string) => {
    setActiveFindingKey(key);
    setActiveAnchorId(anchorId);
    setNavigationRequest((current) => current + 1);
  }, []);

  return (
    <div className={`grid min-h-[620px] gap-4 lg:h-[min(78vh,860px)] ${layout === 'semantic' ? 'lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]' : 'lg:grid-cols-[minmax(0,1.25fr)_minmax(340px,.75fr)]'}`}>
      <PdfPane
        file={file}
        openPdfUrl={openPdfUrl}
        findings={findings}
        activeFindingKey={activeFindingKey}
        activeAnchorId={activeAnchorId}
        navigationRequest={navigationRequest}
        onFindingClick={selectFinding}
        onAnchorClick={selectAnchor}
      />
      <FindingsPane
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
      />
    </div>
  );
}
