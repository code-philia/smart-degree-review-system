import { useCallback, useState } from 'react';
import type { PaperLintRule } from '../../api/paperLint';
import type { RepairSuggestion } from '../../api/repairSuggestions';
import { FindingsPane } from './FindingsPane';
import type { PaperLintFindingItem } from './model';
import { PdfPane } from './PdfPane';

type Props = {
  file: File | { name: string; url: string };
  findings: PaperLintFindingItem[];
  rules: PaperLintRule[];
  openPdfUrl?: string;
  repairSuggestionByFindingKey?: Record<string, RepairSuggestion | undefined>;
  repairSuggestionLoadingKey?: string | null;
  repairSuggestionErrorByFindingKey?: Record<string, string | undefined>;
  onLoadRepairSuggestion?: (finding: PaperLintFindingItem) => void;
  onGenerateRepairSuggestion?: (finding: PaperLintFindingItem) => void;
};

export function PaperLintWorkspace({
  file,
  findings,
  rules,
  openPdfUrl,
  repairSuggestionByFindingKey = {},
  repairSuggestionLoadingKey = null,
  repairSuggestionErrorByFindingKey = {},
  onLoadRepairSuggestion,
  onGenerateRepairSuggestion,
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
    <div className="grid min-h-[620px] gap-4 lg:h-[min(78vh,860px)] lg:grid-cols-[minmax(0,1.25fr)_minmax(340px,.75fr)]">
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
        repairSuggestionErrorByFindingKey={repairSuggestionErrorByFindingKey}
        onLoadRepairSuggestion={onLoadRepairSuggestion}
        onGenerateRepairSuggestion={onGenerateRepairSuggestion}
      />
    </div>
  );
}
