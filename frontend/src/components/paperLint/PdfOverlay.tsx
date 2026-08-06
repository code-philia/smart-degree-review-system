import { memo, useState, type KeyboardEvent } from 'react';
import type { PaperLintPdfAnnotation } from './geometry';

export type HighlightDensity = 'hidden' | 'focus' | 'all';

const colors = {
  error: { fill: 'rgba(239,68,68,.12)', active: 'rgba(239,68,68,.24)', stroke: '#dc2626' },
  warning: { fill: 'rgba(245,158,11,.12)', active: 'rgba(245,158,11,.25)', stroke: '#d97706' },
  info: { fill: 'rgba(59,130,246,.11)', active: 'rgba(59,130,246,.22)', stroke: '#2563eb' },
};

type Props = {
  pageNumber: number;
  pageWidth: number;
  pageHeight: number;
  annotations: PaperLintPdfAnnotation[];
  activeFindingKey: string | null;
  activeAnchorId: string | null;
  density: HighlightDensity;
  onFindingClick: (findingKey: string) => void;
  onAnchorClick: (findingKey: string, anchorId: string) => void;
};

export const PdfOverlay = memo(function PdfOverlay({
  pageNumber,
  pageWidth,
  pageHeight,
  annotations,
  activeFindingKey,
  activeAnchorId,
  density,
  onFindingClick,
  onAnchorClick,
}: Props) {
  const [hovered, setHovered] = useState<string | null>(null);
  if (density === 'hidden') return null;

  return (
    <svg
      data-testid={`paper-lint-overlay-page-${pageNumber}`}
      className="absolute inset-0 size-full"
      viewBox={`0 0 ${pageWidth} ${pageHeight}`}
      preserveAspectRatio="none"
      style={{ pointerEvents: 'none' }}
    >
      <title>{`第 ${pageNumber} 页审查高亮`}</title>
      {annotations.map((annotation) => {
        const active =
          annotation.findingKey === activeFindingKey && (!activeAnchorId || annotation.anchorId === activeAnchorId);
        const hover = annotation.findingKey === hovered;
        const showRects = density === 'all' || active || hover;
        const tone = colors[annotation.severity];
        const marker = annotation.boundingRect;
        const activate = () =>
          annotation.anchorId
            ? onAnchorClick(annotation.findingKey, annotation.anchorId)
            : onFindingClick(annotation.findingKey);
        const onKeyDown = (event: KeyboardEvent<SVGGElement>) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            activate();
          }
        };
        return (
          <g
            key={`${annotation.findingKey}:${annotation.anchorId || 'primary'}:${annotation.pageNumber}`}
            role="button"
            tabIndex={0}
            aria-label={
              annotation.anchorLabel
                ? `${annotation.anchorLabel}：定位第 ${annotation.pageNumber} 页`
                : `定位审查问题：${annotation.textExcerpt || annotation.ruleId}`
            }
            data-testid={`paper-lint-highlight-${annotation.findingKey}${annotation.anchorId ? `-${annotation.anchorId}` : ''}`}
            data-active={String(active)}
            data-finding-key={annotation.findingKey}
            onClick={(event) => {
              event.stopPropagation();
              activate();
            }}
            onKeyDown={onKeyDown}
            onMouseEnter={() => setHovered(annotation.findingKey)}
            onMouseLeave={() => setHovered(null)}
            style={{ cursor: 'pointer', pointerEvents: 'auto' }}
          >
            {density === 'focus' && !showRects ? (
              <rect
                x={Math.max(1, marker.x1 - 8)}
                y={marker.y1}
                width={4}
                height={Math.max(14, marker.y2 - marker.y1)}
                rx={2}
                fill={tone.stroke}
              />
            ) : null}
            {showRects
              ? annotation.rects.map((rect, index) => (
                  <rect
                    key={`${annotation.findingKey}:${index}`}
                    x={rect.x1}
                    y={rect.y1}
                    width={rect.x2 - rect.x1}
                    height={rect.y2 - rect.y1}
                    rx={2}
                    fill={active ? tone.active : tone.fill}
                    stroke={tone.stroke}
                    strokeWidth={active || hover ? 1.5 : 1}
                    vectorEffect="non-scaling-stroke"
                  />
                ))
              : null}
          </g>
        );
      })}
    </svg>
  );
});
