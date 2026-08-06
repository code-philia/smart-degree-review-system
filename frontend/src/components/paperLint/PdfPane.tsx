import { Eye, EyeOff, Highlighter, LoaderCircle, ZoomIn, ZoomOut } from 'lucide-react';
import type { PDFDocumentProxy } from 'pdfjs-dist';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Button } from '../ui';
import type { PaperLintFindingItem } from './model';
import { buildAnnotations, findingTarget, groupAnnotationsByPage } from './geometry';
import { PdfViewer, type PdfViewerHandle } from './PdfViewer';
import type { HighlightDensity } from './PdfOverlay';

type Props = {
  file: File;
  findings: PaperLintFindingItem[];
  activeFindingKey: string | null;
  activeAnchorId: string | null;
  onFindingClick: (key: string) => void;
  onAnchorClick: (key: string, anchorId: string) => void;
};

type Scale = number | 'page-width';

export function PdfPane({ file, findings, activeFindingKey, activeAnchorId, onFindingClick, onAnchorClick }: Props) {
  const [document, setDocument] = useState<PDFDocumentProxy | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [scale, setScale] = useState<Scale>('page-width');
  const [density, setDensity] = useState<HighlightDensity>('focus');
  const viewerRef = useRef<PdfViewerHandle | null>(null);

  useEffect(() => {
    let disposed = false;
    let loaded: PDFDocumentProxy | null = null;
    setDocument(null);
    setError(null);
    void Promise.all([import('pdfjs-dist'), import('pdfjs-dist/build/pdf.worker.min.mjs?url'), file.arrayBuffer()])
      .then(async ([pdfjs, workerModule, buffer]) => {
        pdfjs.GlobalWorkerOptions.workerSrc = workerModule.default;
        const task = pdfjs.getDocument({ data: new Uint8Array(buffer) });
        loaded = await task.promise;
        if (disposed) await loaded.destroy();
        else setDocument(loaded);
      })
      .catch((loadError: unknown) => {
        if (!disposed) setError(loadError instanceof Error ? loadError.message : 'PDF 加载失败');
      });
    return () => {
      disposed = true;
      if (loaded) void loaded.destroy();
    };
  }, [file]);

  const annotationsByPage = useMemo(() => groupAnnotationsByPage(buildAnnotations(findings)), [findings]);
  const activeItem = useMemo(
    () => findings.find((item) => item.key === activeFindingKey) || null,
    [activeFindingKey, findings],
  );
  const target = useMemo(() => findingTarget(activeItem, activeAnchorId), [activeAnchorId, activeItem]);

  useEffect(() => {
    if (!activeFindingKey) return;
    window.requestAnimationFrame(() => {
      if (target.type === 'bbox') viewerRef.current?.scrollToAnnotation(target.annotation);
      else if (target.type === 'page') viewerRef.current?.scrollToPage(target.pageNumber);
    });
  }, [activeFindingKey, activeAnchorId, target]);

  const currentScale = useCallback(
    () => (typeof scale === 'number' ? scale : viewerRef.current?.currentScale() || 1),
    [scale],
  );
  const zoomOut = () => setScale(Math.max(0.5, Number((currentScale() - 0.1).toFixed(2))));
  const zoomIn = () => setScale(Math.min(2.5, Number((currentScale() + 0.1).toFixed(2))));

  return (
    <section className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-3 py-2">
        <div>
          <p className="text-sm font-bold text-slate-900">PDF 原文</p>
          <p className="max-w-80 truncate text-xs text-slate-500">{file.name}</p>
        </div>
        <div className="flex items-center gap-1">
          {(
            [
              ['hidden', EyeOff, '隐藏高亮'],
              ['focus', Eye, '聚焦高亮'],
              ['all', Highlighter, '显示全部高亮'],
            ] as const
          ).map(([value, Icon, label]) => (
            <Button
              key={value}
              size="sm"
              variant={density === value ? 'secondary' : 'ghost'}
              className="px-2"
              aria-label={label}
              aria-pressed={density === value}
              onClick={() => setDensity(value)}
            >
              <Icon className="size-4" />
            </Button>
          ))}
          <Button size="sm" variant="ghost" className="px-2" aria-label="缩小 PDF" onClick={zoomOut}>
            <ZoomOut className="size-4" />
          </Button>
          <Button size="sm" variant="ghost" className="px-2" aria-label="放大 PDF" onClick={zoomIn}>
            <ZoomIn className="size-4" />
          </Button>
        </div>
      </div>
      <div className="relative min-h-[520px] flex-1 overflow-hidden">
        {error ? (
          <div className="flex h-full items-center justify-center p-8 text-center text-sm text-danger-600" role="alert">
            PDF 加载失败：{error}
          </div>
        ) : document ? (
          <PdfViewer
            ref={viewerRef}
            pdfDocument={document}
            scale={scale}
            annotationsByPage={annotationsByPage}
            activeFindingKey={activeFindingKey}
            activeAnchorId={activeAnchorId}
            density={density}
            onFindingClick={onFindingClick}
            onAnchorClick={onAnchorClick}
          />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-slate-500">
            <LoaderCircle className="mr-2 size-4 animate-spin" />
            正在加载 PDF…
          </div>
        )}
      </div>
    </section>
  );
}
