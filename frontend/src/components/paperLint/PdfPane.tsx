import { Eye, EyeOff, Highlighter, Link2, LoaderCircle, RefreshCw, ZoomIn, ZoomOut } from 'lucide-react';
import type { PDFDocumentLoadingTask, PDFDocumentProxy } from 'pdfjs-dist';
import { loadPdfJs, pdfResourceOptions } from '../../pdfRuntime';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Button, buttonClassName } from '../ui';
import type { PaperLintFindingItem } from './model';
import { buildAnnotations, findingTarget, groupAnnotationsByPage } from './geometry';
import { PdfViewer, preloadPdfViewer, type PdfViewerHandle, type SupplementalPdfAnnotation } from './PdfViewer';
import type { HighlightDensity } from './PdfOverlay';
import { findingPageLabel } from './model';
import { resolvePdfPageLabels, type PdfPageLabels } from './pageLabels';

type Props = {
  file: File | { name: string; url: string };
  openPdfUrl?: string;
  findings: PaperLintFindingItem[];
  activeFindingKey: string | null;
  activeAnchorId: string | null;
  navigationRequest?: number;
  requestedPage?: number | null;
  onFindingClick: (key: string) => void;
  onAnchorClick: (key: string, anchorId: string) => void;
  onPageLabels?: (labels: PdfPageLabels) => void;
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
const PDF_INACTIVITY_TIMEOUT_MS = 45_000;

function previewError(cause: unknown) {
  const message = cause instanceof Error ? cause.message : String(cause || '');
  if (/超时|长时间/.test(message)) return message;
  if (/401|403|Unauthorized|Forbidden/.test(message)) return '登录状态已过期或没有文档访问权限，请重新登录后重试。';
  if (/InvalidPDF|Invalid PDF|MissingPDF|404/.test(message)) return 'PDF 文件无效或暂不可用，请重新加载或打开完整 PDF。';
  return 'PDF 预览暂时无法加载，请检查网络后重试，也可打开完整 PDF。';
}

export function PdfPane({
  file,
  openPdfUrl,
  findings,
  activeFindingKey,
  activeAnchorId,
  navigationRequest = 0,
  requestedPage = null,
  onFindingClick,
  onAnchorClick,
  onPageLabels,
  onTextSelection,
  supplementalAnnotations = EMPTY_SUPPLEMENTAL_ANNOTATIONS,
  activeSupplementalAnnotationId = null,
  onSupplementalAnnotationClick,
}: Props) {
  const [document, setDocument] = useState<PDFDocumentProxy | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [phase, setPhase] = useState<'loading' | 'rendering' | 'ready' | 'error'>('loading');
  const [receivedBytes, setReceivedBytes] = useState(0);
  const lifecycleRef = useRef<{ ready: () => void; fail: (error: unknown) => void } | null>(null);
  const handleReady = useCallback(() => lifecycleRef.current?.ready(), []);
  const handleError = useCallback((error: unknown) => lifecycleRef.current?.fail(error), []);
  const [scale, setScale] = useState<Scale>('page-width');
  const [density, setDensity] = useState<HighlightDensity>('focus');
  const viewerRef = useRef<PdfViewerHandle | null>(null);

  const sourceUrl = 'url' in file ? file.url : null;
  const sourceFile = 'url' in file ? null : file;
  useEffect(() => {
    let disposed = false, failed = false, painted = false;
    let task: PDFDocumentLoadingTask | null = null;
    let deadline: ReturnType<typeof setTimeout>;
    let lastReceived = 0;
    const destroyTask = () => { if (task) void Promise.resolve(task.destroy()).catch(() => {}); };
    function fail(cause: unknown) {
      if (disposed || failed) return;
      failed = true;
      clearTimeout(deadline);
      setDocument(null);
      setPhase('error');
      setError(previewError(cause));
      destroyTask();
    }
    function armDeadline(message: string) {
      clearTimeout(deadline);
      deadline = setTimeout(() => fail(new Error(message)), PDF_INACTIVITY_TIMEOUT_MS);
    }
    lifecycleRef.current = {
      fail,
      ready() {
        if (disposed || failed) return;
        painted = true;
        clearTimeout(deadline);
        setPhase('ready');
      },
    };
    setDocument(null);
    setError(null);
    setPhase('loading');
    setReceivedBytes(0);
    armDeadline('PDF 加载长时间没有响应，请重新加载或打开完整 PDF。');
    // Download the viewer alongside the document, instead of a second waterfall.
    const viewerReady = preloadPdfViewer();
    void viewerReady.catch(fail);
    void loadPdfJs().then(async (pdfjs) => {
      if (disposed || failed) return;
      const data = sourceFile ? new Uint8Array(await sourceFile.arrayBuffer()) : undefined;
      if (disposed || failed) return;
      task = pdfjs.getDocument({
        ...(sourceUrl !== null ? { url: sourceUrl, withCredentials: true, disableStream: true, rangeChunkSize: 262144 } : { data }),
        disableAutoFetch: true,
        ...pdfResourceOptions(pdfjs.version),
      });
      task.onProgress = ({ loaded }: { loaded: number; total: number }) => {
        if (disposed || failed || painted || loaded <= lastReceived) return;
        lastReceived = loaded;
        setReceivedBytes(loaded);
        armDeadline('PDF 下载长时间没有进展，请检查网络后重新加载。');
      };
      const loaded = await task.promise;
      if (disposed || failed) return;
      setDocument(loaded);
      setPhase('rendering');
      armDeadline('PDF 页面渲染超时，请重新加载或打开完整 PDF。');
    }).catch(fail);
    return () => {
      disposed = true;
      clearTimeout(deadline);
      lifecycleRef.current = null;
      destroyTask();
    };
  }, [sourceUrl, sourceFile, attempt]);

  const annotationsByPage = useMemo(() => groupAnnotationsByPage(buildAnnotations(findings)), [findings]);
  const labelPageKey = [...new Set([
    ...findings.flatMap(item => findingPageLabel(item)?.split('、').map(Number) || []),
    ...supplementalAnnotations.map(item => item.pageNumber),
    ...(requestedPage ? [requestedPage] : []),
  ])].sort((a, b) => a - b).join(',');
  useEffect(() => {
    onPageLabels?.({});
    if (!document || phase !== 'ready' || !onPageLabels) return;
    const controller = new AbortController();
    void resolvePdfPageLabels(document, labelPageKey.split(',').map(Number), { signal: controller.signal, onUpdate: onPageLabels }).catch(() => {});
    return () => controller.abort();
  }, [document, phase, labelPageKey, onPageLabels]);
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
    if (!activeFindingKey && !requestedPage) return;
    window.requestAnimationFrame(() => {
      if (requestedPage) viewerRef.current?.scrollToPage(requestedPage);
      else if (target.type === 'bbox') viewerRef.current?.scrollToAnnotation(target.annotation);
      else if (target.type === 'page') viewerRef.current?.scrollToPage(target.pageNumber);
    });
  }, [activeFindingKey, activeAnchorId, target, document, navigationRequest, requestedPage]);

  const currentScale = useCallback(
    () => (typeof scale === 'number' ? scale : viewerRef.current?.currentScale() || 1),
    [scale],
  );
  const zoomOut = () => setScale(Math.max(0.5, Number((currentScale() - 0.1).toFixed(2))));
  const zoomIn = () => setScale(Math.min(2.5, Number((currentScale() + 0.1).toFixed(2))));

  return (
    <section data-pdf-status={phase} aria-busy={phase === 'loading' || phase === 'rendering'} className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-3 py-2">
        <div className="min-w-0 flex-1">
          <p className="line-clamp-2 text-sm font-bold text-slate-900" title={file.name}>文档名称：{file.name}</p>
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
              href={browserPdfUrl || undefined}
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
        {phase === 'rendering' ? <div role="status" className="pointer-events-none absolute inset-x-0 top-3 z-20 mx-auto flex w-fit items-center gap-2 rounded-full border border-slate-200 bg-white/95 px-4 py-2 text-xs text-slate-600 shadow-sm"><LoaderCircle className="size-3.5 animate-spin" />正在渲染 PDF…</div> : null}
        {error ? (
          <div className="flex h-full min-h-[520px] flex-col items-center justify-center gap-4 p-8 text-center" role="alert">
            <p className="max-w-sm text-sm leading-6 text-slate-700">{error}</p>
            <div className="flex flex-wrap justify-center gap-3">
              <Button size="sm" onClick={() => setAttempt(value => value + 1)}><RefreshCw className="size-4" />重新加载 PDF</Button>
              {browserPdfUrl ? <a href={browserPdfUrl} target="_blank" rel="noopener noreferrer" className={buttonClassName('secondary', 'sm')}>打开完整 PDF</a> : null}
            </div>
          </div>
        ) : document ? (
          <PdfViewer
            ref={viewerRef}
            pdfDocument={document}
            onReady={handleReady}
            onError={handleError}
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
          <div role="status" className="flex h-full min-h-[520px] items-center justify-center text-sm text-slate-500">
            <LoaderCircle className="mr-2 size-4 animate-spin" />
            正在加载 PDF…{receivedBytes > 0 ? `已接收 ${(receivedBytes / 1024 / 1024).toFixed(1)} MB` : ''}
          </div>
        )}
      </div>
    </section>
  );
}
