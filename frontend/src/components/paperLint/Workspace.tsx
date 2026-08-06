import { useCallback, useState } from 'react';
import type { PaperLintRule } from '../../api/paperLint';
import { FindingsPane } from './FindingsPane';
import type { PaperLintFindingItem } from './model';
import { PdfPane } from './PdfPane';

type Props = { file: File; findings: PaperLintFindingItem[]; rules: PaperLintRule[] };

export function PaperLintWorkspace({ file, findings, rules }: Props) {
  const [activeFindingKey, setActiveFindingKey] = useState<string | null>(findings[0]?.key || null);
  const [activeAnchorId, setActiveAnchorId] = useState<string | null>(null);
  const selectFinding = useCallback((key: string) => {
    setActiveFindingKey(key);
    setActiveAnchorId(null);
  }, []);
  const selectAnchor = useCallback((key: string, anchorId: string) => {
    setActiveFindingKey(key);
    setActiveAnchorId(anchorId);
  }, []);

  return (
    <div className="grid min-h-[620px] gap-4 lg:h-[min(78vh,860px)] lg:grid-cols-[minmax(0,1.25fr)_minmax(340px,.75fr)]">
      <PdfPane
        file={file}
        findings={findings}
        activeFindingKey={activeFindingKey}
        activeAnchorId={activeAnchorId}
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
      />
    </div>
  );
}
