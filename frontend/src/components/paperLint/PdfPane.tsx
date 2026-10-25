import { Eye, EyeOff, Highlighter, Link2, LoaderCircle, ZoomIn, ZoomOut } from 'lucide-react';
import type { PDFDocumentLoadingTask, PDFDocumentProxy } from 'pdfjs-dist';
import pdfWorkerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Button, buttonClassName } from '../ui';
import type { PaperLintFindingItem } from './model';
import { buildAnnotations, findingTarget, groupAnnotationsByPage } from './geometry';
import { PdfViewer, type PdfViewerHandle, type SupplementalPdfAnnotation } from './PdfViewer';
import type { HighlightDensity } from './PdfOverlay';

type Props = {
  file: File | { name: string; url: string };
  openPdfUrl?: string;
  findings: PaperLintFindingItem[];
  activeFindingKey: string | null;
  activeAnchorId: string | null;
  navigationRequest?: number;
  onFindingClick: (key: string) => void;
  onAnchorClick: (key: string, anchorId: string) => void;
  onTextSelection?: (selection: {
    pageNumber: number;
    text: string;
    boundingRect: {
      x1: number;
      y1: number;
      x2: number;
      y2: number;
      width: number;
      height: number;
      page_number: number;
    };
  }) => void;
  supplementalAnnotations?: SupplementalPdfAnnotation[];
  activeSupplementalAnnotationId?: string | null;
  onSupplementalAnnotationClick?: (id: string) => void;
};

type Scale = number | 'page-width';
const EMPTY_SUPPLEMENTAL_ANNOTATIONS: SupplementalPdfAnnotation[] = [];
const cMapOptions = { cMapUrl: `${import.meta.env.BASE_URL}pdfjs-cmaps/`, cMapPacked: true };

export function PdfPane({
  file,
  openPdfUrl,
  findings,
  activeFindingKey,
  activeAnchorId,
  navigationRequest = 0,
  onFindingClick,
  onAnchorClick,
  onTextSelection,
  supplementalAnnotations = EMPTY_SUPPLEMENTAL_ANNOTATIONS,
  activeSupplementalAnnotationId = null,
  onSupplementalAnnotationClick,
}: Props) {
  const [document, setDocument] = useState<PDFDocumentProxy | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [scale, setScale] = useState<Scale>('page-width');
  const [density, setDensity] = useState<HighlightDensity>('focus');
  const viewerRef = useRef<PdfViewerHandle | null>(null);

  const sourceUrl = 'url' in file ? file.url : null;
  const sourceFile = 'url' in file ? null : file;
  useEffect(() => {
    let disposed = false;
    let task: PDFDocumentLoadingTask | null = null;
    setDocument(null);
    setError(null);
    void import('pdfjs-dist')
      .then(async (pdfjs) => {
        if (disposed) return;
        pdfjs.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;
        const data = sourceFile ? new Uint8Array(await sourceFile.arrayBuffer()) : undefined;
        if (disposed) return;
        task = sourceUrl !== null
          ? pdfjs.getDocument({
              url: sourceUrl,
              withCredentials: true,
              disableAutoFetch: true,
              disableStream: true,
              rangeChunkSize: 262144,
              ...cMapOptions,
            })
          : pdfjs.getDocument({ data, disableAutoFetch: true, ...cMapOptions });
        const loaded = await task.promise;
        if (!disposed) setDocument(loaded);
      })
      .catch((loadError: unknown) => {
        if (!disposed) setError(loadError instanceof Error ? loadError.message : 'PDF 加载失败');
      });
    return () => {
      disposed = true;
      if (task) void task.destroy();
    };
  }, [sourceUrl, sourceFile]);

  const annotationsByPage = useMemo(() => groupAnnotationsByPage(buildAnnotations(findings)), [findings]);
  const activeItem = useMemo(
    () => findings.find((item) => item.key === activeFindingKey) || null,
    [activeFindingKey, findings],
  );
  const target = useMemo(() => findingTarget(activeItem, activeAnchorId), [activeAnchorId, activeItem]);
  const pageNumber =
    target.type === 'bbox' ? target.annotation.pageNumber : target.type === 'page' ? target.pageNumber : null;
  const fullPdfUrl = openPdfUrl || sourceUrl;
  const browserPdfUrl =
    fullPdfUrl && pageNumber && Number.isInteger(pageNumber) && pageNumber > 0
      ? `${fullPdfUrl.split('#')[0]}#page=${pageNumber}`
      : fullPdfUrl;

  useEffect(() => {
    if (!activeFindingKey) return;
    window.requestAnimationFrame(() => {
      if (target.type === 'bbox') viewerRef.current?.scrollToAnnotation(target.annotation);
      else if (target.type === 'page') viewerRef.current?.scrollToPage(target.pageNumber);
    });
  }, [activeFindingKey, activeAnchorId, target, document, navigationRequest]);

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
        <div role="toolbar" aria-label="PDF 工具" className="flex items-center gap-1">
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
              title={label}
              aria-pressed={density === value}
              onClick={() => setDensity(value)}
            >
              <Icon className="size-4" />
            </Button>
          ))}
          <Button size="sm" variant="ghost" className="px-2" aria-label="缩小 PDF" title="缩小 PDF" onClick={zoomOut}>
            <ZoomOut className="size-4" />
          </Button>
          <Button size="sm" variant="ghost" className="px-2" aria-label="放大 PDF" title="放大 PDF" onClick={zoomIn}>
            <ZoomIn className="size-4" />
          </Button>
          {fullPdfUrl ? (
            <a
              href={browserPdfUrl}
              target="_blank"
              rel="noopener noreferrer"
              className={buttonClassName('ghost', 'sm', 'px-2')}
              aria-label="在浏览器打开完整 PDF"
              title="在浏览器打开完整 PDF"
            >
              <Link2 className="size-4" />
            </a>
          ) : null}
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
            onTextSelection={onTextSelection}
            supplementalAnnotations={supplementalAnnotations}
            activeSupplementalAnnotationId={activeSupplementalAnnotationId}
            onSupplementalAnnotationClick={onSupplementalAnnotationClick}
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
