import { ChevronDown, ChevronLeft, ChevronRight, Eye, EyeOff, Highlighter, Link2, LoaderCircle, RefreshCw, SlidersHorizontal, ZoomIn, ZoomOut } from 'lucide-react';
import type { PDFDocumentLoadingTask, PDFDocumentProxy } from 'pdfjs-dist';
import { loadPdfJs, pdfResourceOptions } from '../../pdfRuntime';

import { type FormEvent, useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import { Button, buttonClassName } from '../ui';
import type { PaperLintFindingItem } from './model';
import { buildAnnotations, findingTarget, groupAnnotationsByPage } from './geometry';
import { PdfViewer, preloadPdfViewer, type PdfViewerHandle, type SupplementalPdfAnnotation } from './PdfViewer';
import type { HighlightDensity } from './PdfOverlay';
import { findingPageLabel } from './model';
import { resolvePdfPageLabels, type PdfPageLabels } from './pageLabels';
import { REPORT_DOCUMENT_TEXT } from './documentTypography';

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
  const [currentPage, setCurrentPage] = useState(1);
  const [pageInput, setPageInput] = useState('1');
  const [pageError, setPageError] = useState<string | null>(null);
  const editingPageRef = useRef(false);
  const pageHelpId = useId();
  const pageErrorId = useId();
  const toolbarId = useId();
  const [toolbarExpanded, setToolbarExpanded] = useState(false);
  const pageCount = document && Number.isSafeInteger(document.numPages) && document.numPages > 0 ? document.numPages : 0;
  const canNavigate = phase === 'ready' && pageCount > 0;
  const handlePageChange = useCallback((page: number) => {
    if (!Number.isSafeInteger(page) || page < 1 || page > pageCount) return;
    setCurrentPage(page);
    if (!editingPageRef.current) setPageInput(String(page));
    setPageError(null);
  }, [pageCount]);

  const sourceUrl = 'url' in file ? file.url : null;
  const sourceFile = 'url' in file ? null : file;
  const [uploadedPdf, setUploadedPdf] = useState<{ file: File; url: string } | null>(null);
  useEffect(() => {
    if (!sourceFile || openPdfUrl || !(sourceFile instanceof Blob) || typeof URL.createObjectURL !== 'function') return;
    const url = URL.createObjectURL(sourceFile);
    setUploadedPdf({ file: sourceFile, url });
    return () => URL.revokeObjectURL(url);
  }, [sourceFile, openPdfUrl]);
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
    setCurrentPage(1);
    setPageInput('1');
    setPageError(null);
    editingPageRef.current = false;
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
  const fullPdfUrl = openPdfUrl || sourceUrl || (uploadedPdf?.file === sourceFile ? uploadedPdf?.url : null);
  const browserPage = phase === 'ready' ? currentPage : requestedPage || pageNumber;
  const browserPdfUrl =
    fullPdfUrl && browserPage && Number.isInteger(browserPage) && browserPage > 0
      ? `${fullPdfUrl.split('#')[0]}#page=${browserPage}`
      : fullPdfUrl;

  const lastNavigationRef = useRef<{
    document: PDFDocumentProxy;
    findingKey: string | null;
    anchorId: string | null;
    request: number;
    page: number | null;
  } | null>(null);

  useEffect(() => {
    if (!document || (!activeFindingKey && !requestedPage)) return;
    if (!requestedPage && target.type === 'none') return;
    const previous = lastNavigationRef.current;
    if (previous?.document === document && previous.findingKey === activeFindingKey &&
      previous.anchorId === activeAnchorId && previous.request === navigationRequest && previous.page === requestedPage) return;
    const frame = window.requestAnimationFrame(() => {
      const viewer = viewerRef.current;
      if (!viewer) return;
      if (requestedPage) viewer.scrollToPage(requestedPage);
      else if (target.type === 'bbox') viewer.scrollToAnnotation(target.annotation);
      else if (target.type === 'page') viewer.scrollToPage(target.pageNumber);
      lastNavigationRef.current = { document, findingKey: activeFindingKey, anchorId: activeAnchorId, request: navigationRequest, page: requestedPage };
    });
    return () => window.cancelAnimationFrame(frame);
  }, [activeFindingKey, activeAnchorId, target, document, navigationRequest, requestedPage]);

  const currentScale = useCallback(
    () => (typeof scale === 'number' ? scale : viewerRef.current?.currentScale() || 1),
    [scale],
  );
  const zoomOut = () => setScale(Math.max(0.5, Number((currentScale() - 0.1).toFixed(2))));
  const zoomIn = () => setScale(Math.min(2.5, Number((currentScale() + 0.1).toFixed(2))));
  const goToPage = (page: number) => {
    if (!canNavigate || !viewerRef.current) return;
    if (!Number.isSafeInteger(page) || page < 1 || page > pageCount) {
      setPageError(`请输入 1–${pageCount} 范围内的整数页码。`);
      return;
    }
    editingPageRef.current = false;
    setPageInput(String(page));
    setCurrentPage(page);
    setPageError(null);
    viewerRef.current.scrollToPage(page);
  };
  const submitPage = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const value = pageInput.trim();
    goToPage(/^\d+$/.test(value) ? Number(value) : NaN);
  };

  return (
    <section data-pdf-status={phase} aria-busy={phase === 'loading' || phase === 'rendering'} className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white">
      <div className="@container border-b border-slate-200 bg-white">
        <div className="flex h-12 min-w-0 items-center gap-3 px-3">
          <p className={`min-w-0 flex-1 truncate text-slate-600 ${REPORT_DOCUMENT_TEXT}`} title={file.name}><span className="sr-only">文档名称：</span>{file.name}</p>
          <button
            type="button"
            className={`inline-flex h-8 shrink-0 cursor-pointer items-center gap-2 rounded-lg border px-2.5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/25 focus-visible:ring-offset-2 motion-reduce:transition-none ${REPORT_DOCUMENT_TEXT} ${toolbarExpanded ? 'border-brand-500/25 bg-brand-50 text-brand-700' : 'border-slate-200 bg-white text-slate-600 shadow-xs hover:border-slate-300 hover:bg-slate-50'}`}
            aria-expanded={toolbarExpanded}
            aria-controls={toolbarId}
            aria-label={toolbarExpanded ? '收起阅读工具' : '展开阅读工具'}
            title={toolbarExpanded ? '收起阅读工具' : '展开阅读工具'}
            onClick={() => setToolbarExpanded(value => !value)}
          >
            <SlidersHorizontal aria-hidden="true" className="size-4 shrink-0" />
            <span>阅读工具</span>
            <ChevronDown aria-hidden="true" className={`size-3.5 shrink-0 transition-transform motion-reduce:transition-none ${toolbarExpanded ? 'rotate-180' : ''}`} />
          </button>
        </div>
        <div id={toolbarId} hidden={!toolbarExpanded}>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-slate-100 bg-slate-50/80 px-3 py-2">
          <form aria-label="PDF 页码跳转" onSubmit={submitPage} className="flex w-full items-center justify-center gap-1.5 @[32rem]:w-auto @[32rem]:justify-start">
            <Button type="button" size="sm" variant="ghost" className="w-8 shrink-0 px-0! [&>svg]:shrink-0" aria-label="PDF 上一页" title="上一页" disabled={!canNavigate || currentPage <= 1} onClick={() => goToPage(currentPage - 1)}>
              <ChevronLeft className="size-4" />
            </Button>
            <div className="flex h-8 items-center rounded-lg border border-slate-200 bg-white [font-family:var(--font-app)] text-xs leading-5 tabular-nums transition focus-within:border-brand-400 focus-within:ring-2 focus-within:ring-brand-100">
              <input
                type="text" inputMode="numeric" enterKeyHint="go"
                aria-label="PDF 页码" title="输入 PDF 页码，按 Enter 跳转"
                aria-describedby={pageError ? `${pageHelpId} ${pageErrorId}` : pageHelpId}
                aria-invalid={pageError ? true : undefined}
                disabled={!canNavigate} value={pageInput}
                className="h-5 w-11 min-w-0 rounded-l-lg bg-transparent px-1 text-center [font-family:inherit] text-xs font-medium leading-5 text-slate-900 outline-none disabled:text-slate-400"
                onFocus={event => event.currentTarget.select()}
                onChange={event => { editingPageRef.current = true; setPageInput(event.target.value); setPageError(null); }}
                onBlur={() => { editingPageRef.current = false; }}
              />
              <span className="flex h-5 items-center text-slate-300" aria-hidden="true">/</span>
              <span title="PDF 总页数" className="flex h-5 min-w-10 items-center justify-center px-2 text-center [font-family:inherit] text-xs font-medium leading-5 text-slate-500">{pageCount || '—'}</span>
            </div>
            <Button type="button" size="sm" variant="ghost" className="w-8 shrink-0 px-0! [&>svg]:shrink-0" aria-label="PDF 下一页" title="下一页" disabled={!canNavigate || currentPage >= pageCount} onClick={() => goToPage(currentPage + 1)}>
              <ChevronRight className="size-4" />
            </Button>
          </form>
          <div role="toolbar" aria-label="PDF 工具" className="flex w-full items-center justify-center gap-2 @[32rem]:ml-auto @[32rem]:w-auto">
            <div role="group" aria-label="高亮显示" className="flex items-center gap-0.5 rounded-lg bg-slate-200/50 p-0.5">
              {([
                ['hidden', EyeOff, '隐藏高亮'],
                ['focus', Eye, '聚焦高亮'],
                ['all', Highlighter, '显示全部高亮'],
              ] as const).map(([value, Icon, label]) => (
                <Button
                  key={value}
                  size="sm"
                  variant="ghost"
                  className={`w-8 shrink-0 px-0! [&>svg]:shrink-0 ${density === value ? 'bg-white text-brand-600! shadow-sm hover:bg-white! hover:text-brand-700!' : 'text-slate-500'}`}
                  aria-label={label}
                  title={label}
                  aria-pressed={density === value}
                  onClick={() => setDensity(value)}
                >
                  <Icon className="size-4" />
                </Button>
              ))}
            </div>
            <span aria-hidden="true" className="h-4 w-px bg-slate-200" />
            <div role="group" aria-label="PDF 缩放" className="flex items-center gap-0.5">
              <Button size="sm" variant="ghost" className="w-8 shrink-0 px-0! [&>svg]:shrink-0" aria-label="缩小 PDF" title="缩小 PDF" onClick={zoomOut}>
                <ZoomOut className="size-4" />
              </Button>
              <Button size="sm" variant="ghost" className="w-8 shrink-0 px-0! [&>svg]:shrink-0" aria-label="放大 PDF" title="放大 PDF" onClick={zoomIn}>
                <ZoomIn className="size-4" />
              </Button>
            </div>
            {fullPdfUrl ? <>
              <span aria-hidden="true" className="h-4 w-px bg-slate-200" />
              <a
                href={browserPdfUrl || undefined}
                target="_blank"
                rel="noopener noreferrer"
                className={buttonClassName('ghost', 'sm', 'w-8 shrink-0 px-0! [&>svg]:shrink-0')}
                aria-label="在浏览器打开完整 PDF"
                title="在浏览器打开完整 PDF"
              >
                <Link2 className="size-4" />
              </a>
            </> : null}
          </div>
        </div>
        <span id={pageHelpId} className="sr-only">按 PDF 实际页序计数，输入页码后按 Enter 跳转。</span>
        {pageError ? <p id={pageErrorId} role="alert" className="border-t border-slate-100 px-4 py-2 text-xs leading-5 text-rose-600">{pageError}</p> : null}
        </div>
      </div>
      <div className="relative min-h-[var(--pdf-preview-min-height,520px)] flex-1 overflow-hidden">
        {phase === 'rendering' ? <div role="status" className="pointer-events-none absolute inset-x-0 top-3 z-20 mx-auto flex w-fit items-center gap-2 rounded-full border border-slate-200 bg-white/95 px-4 py-2 text-xs text-slate-600 shadow-sm"><LoaderCircle className="size-3.5 animate-spin" />正在渲染 PDF…</div> : null}
        {error ? (
          <div className="flex h-full min-h-[var(--pdf-preview-min-height,520px)] flex-col items-center justify-center gap-4 p-8 text-center" role="alert">
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
            onPageChange={handlePageChange}
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
          <div role="status" className="flex h-full min-h-[var(--pdf-preview-min-height,520px)] items-center justify-center text-sm text-slate-500">
            <LoaderCircle className="mr-2 size-4 animate-spin" />
            正在加载 PDF…{receivedBytes > 0 ? `已接收 ${(receivedBytes / 1024 / 1024).toFixed(1)} MB` : ''}
          </div>
        )}
      </div>
    </section>
  );
}
