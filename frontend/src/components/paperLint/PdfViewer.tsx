import 'pdfjs-dist/web/pdf_viewer.css';

import type { PDFDocumentProxy } from 'pdfjs-dist';
import { forwardRef, memo, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { getPdfRectCenter, pageSize, type PaperLintPdfAnnotation } from './geometry';
import { PdfOverlay, type HighlightDensity } from './PdfOverlay';

type ViewerModule = typeof import('pdfjs-dist/web/pdf_viewer.mjs');
type PdfJsModule = typeof import('pdfjs-dist');
type EventBus = InstanceType<ViewerModule['EventBus']>;
type LinkService = InstanceType<ViewerModule['PDFLinkService']>;
type Viewer = InstanceType<ViewerModule['PDFViewer']>;
type Scale = number | 'page-width';

let viewerModulePromise: Promise<ViewerModule> | null = null;

function loadViewerModule() {
  if (!viewerModulePromise) {
    viewerModulePromise = import('pdfjs-dist').then((pdfjsLib) => {
      (globalThis as typeof globalThis & { pdfjsLib?: PdfJsModule }).pdfjsLib = pdfjsLib;
      return import('pdfjs-dist/web/pdf_viewer.mjs');
    });
  }
  return viewerModulePromise;
}

export type PdfViewerHandle = {
  scrollToPage: (pageNumber: number) => void;
  scrollToAnnotation: (annotation: PaperLintPdfAnnotation) => void;
  currentScale: () => number;
};

type Props = {
  pdfDocument: PDFDocumentProxy;
  scale: Scale;
  annotationsByPage: Map<number, PaperLintPdfAnnotation[]>;
  activeFindingKey: string | null;
  activeAnchorId: string | null;
  density: HighlightDensity;
  onFindingClick: (findingKey: string) => void;
  onAnchorClick: (findingKey: string, anchorId: string) => void;
};

type ViewerState = { eventBus: EventBus; linkService: LinkService; viewer: Viewer };
type OverlayHost = { pageNumber: number; host: HTMLDivElement };

function pageElement(container: HTMLDivElement, pageNumber: number) {
  return container.querySelector<HTMLElement>(`.page[data-page-number="${pageNumber}"]`);
}

function overlayHost(element: HTMLElement, pageNumber: number) {
  const existing = element.querySelector<HTMLDivElement>('.paper-lint-overlay-host');
  if (existing) return existing;
  if (!element.style.position) element.style.position = 'relative';
  const host = document.createElement('div');
  host.className = 'paper-lint-overlay-host absolute inset-0';
  host.dataset.pageNumber = String(pageNumber);
  host.style.pointerEvents = 'none';
  element.appendChild(host);
  return host;
}

function scrollToRect(container: HTMLDivElement, element: HTMLElement, annotation: PaperLintPdfAnnotation) {
  const center = getPdfRectCenter(annotation.boundingRect);
  const scaleX = element.clientWidth / annotation.boundingRect.width;
  const scaleY = element.clientHeight / annotation.boundingRect.height;
  container.scrollTo({
    top: Math.max(0, element.offsetTop + center.y * scaleY - container.clientHeight / 2),
    left: Math.max(0, element.offsetLeft + center.x * scaleX - container.clientWidth / 2),
    behavior: 'smooth',
  });
}

export const PdfViewer = memo(
  forwardRef<PdfViewerHandle, Props>(function PdfViewer(
    { pdfDocument, scale, annotationsByPage, activeFindingKey, activeAnchorId, density, onFindingClick, onAnchorClick },
    ref,
  ) {
    const containerRef = useRef<HTMLDivElement | null>(null);
    const viewerRef = useRef<HTMLDivElement | null>(null);
    const stateRef = useRef<ViewerState | null>(null);
    const pendingRef = useRef<PaperLintPdfAnnotation | null>(null);
    const annotationsRef = useRef(annotationsByPage);
    const scaleRef = useRef(scale);
    const [hosts, setHosts] = useState<OverlayHost[]>([]);

    useEffect(() => {
      annotationsRef.current = annotationsByPage;
    }, [annotationsByPage]);
    useEffect(() => {
      scaleRef.current = scale;
    }, [scale]);

    const syncHosts = useCallback(() => {
      const container = containerRef.current;
      if (!container) return;
      const next = Array.from(annotationsRef.current.keys()).flatMap((pageNumber) => {
        const element = pageElement(container, pageNumber);
        return element ? [{ pageNumber, host: overlayHost(element, pageNumber) }] : [];
      });
      setHosts((previous) =>
        previous.length === next.length &&
        previous.every((item, index) => item.pageNumber === next[index].pageNumber && item.host === next[index].host)
          ? previous
          : next,
      );
    }, []);

    const scrollToPage = useCallback((pageNumber: number) => {
      stateRef.current?.viewer.scrollPageIntoView({ pageNumber });
    }, []);

    const scrollToAnnotation = useCallback((annotation: PaperLintPdfAnnotation) => {
      const container = containerRef.current;
      const state = stateRef.current;
      if (!container || !state) {
        pendingRef.current = annotation;
        return;
      }
      state.viewer.scrollPageIntoView({ pageNumber: annotation.pageNumber });
      window.requestAnimationFrame(() => {
        const element = pageElement(container, annotation.pageNumber);
        if (element) scrollToRect(container, element, annotation);
        else pendingRef.current = annotation;
      });
    }, []);

    const flushPending = useCallback(() => {
      const annotation = pendingRef.current;
      const container = containerRef.current;
      if (!annotation || !container) return;
      const element = pageElement(container, annotation.pageNumber);
      if (!element) return;
      pendingRef.current = null;
      scrollToRect(container, element, annotation);
    }, []);

    useImperativeHandle(
      ref,
      () => ({
        scrollToPage,
        scrollToAnnotation,
        currentScale: () => stateRef.current?.viewer.currentScale || 1,
      }),
      [scrollToAnnotation, scrollToPage],
    );

    useEffect(() => {
      const container = containerRef.current;
      const viewerElement = viewerRef.current;
      if (!container || !viewerElement) return;
      let disposed = false;
      let cleanup: (() => void) | null = null;
      const onPageRendered = () => {
        syncHosts();
        flushPending();
      };
      const onScaleChanging = () => window.requestAnimationFrame(syncHosts);

      void loadViewerModule().then(({ EventBus, PDFLinkService, PDFViewer }) => {
        if (disposed) return;
        const eventBus = new EventBus();
        const linkService = new PDFLinkService({ eventBus });
        const viewer = new PDFViewer({
          container,
          viewer: viewerElement,
          eventBus,
          linkService,
          textLayerMode: 0,
          annotationMode: 0,
          removePageBorders: true,
        });
        linkService.setViewer(viewer);
        linkService.setDocument(pdfDocument);
        viewer.setDocument(pdfDocument);
        stateRef.current = { eventBus, linkService, viewer };
        eventBus.on('pagerendered', onPageRendered);
        eventBus.on('scalechanging', onScaleChanging);
        container.addEventListener('scroll', syncHosts, { passive: true });
        if (typeof scaleRef.current === 'number') viewer.currentScale = scaleRef.current;
        else viewer.currentScaleValue = scaleRef.current;
        cleanup = () => {
          eventBus.off('pagerendered', onPageRendered);
          eventBus.off('scalechanging', onScaleChanging);
          container.removeEventListener('scroll', syncHosts);
          viewer.cleanup();
        };
      });
      return () => {
        disposed = true;
        cleanup?.();
        stateRef.current = null;
        setHosts([]);
      };
    }, [flushPending, pdfDocument, syncHosts]);

    useEffect(() => {
      const viewer = stateRef.current?.viewer;
      if (!viewer) return;
      if (typeof scale === 'number') viewer.currentScale = scale;
      else viewer.currentScaleValue = scale;
      window.requestAnimationFrame(syncHosts);
    }, [scale, syncHosts]);

    useEffect(() => {
      syncHosts();
    }, [annotationsByPage, syncHosts]);

    const portals = useMemo(
      () =>
        hosts.flatMap(({ pageNumber, host }) => {
          const annotations = annotationsByPage.get(pageNumber) || [];
          const size = pageSize(annotations);
          if (!size) return [];
          return [
            createPortal(
              <PdfOverlay
                pageNumber={pageNumber}
                pageWidth={size.width}
                pageHeight={size.height}
                annotations={annotations}
                activeFindingKey={activeFindingKey}
                activeAnchorId={activeAnchorId}
                density={density}
                onFindingClick={onFindingClick}
                onAnchorClick={onAnchorClick}
              />,
              host,
              `paper-lint-overlay-${pageNumber}`,
            ),
          ];
        }),
      [activeAnchorId, activeFindingKey, annotationsByPage, density, hosts, onAnchorClick, onFindingClick],
    );

    return (
      <div
        ref={containerRef}
        data-testid="paper-lint-pdf-viewer"
        className="absolute inset-0 overflow-auto bg-slate-200/70"
      >
        <div ref={viewerRef} className="pdfViewer" />
        {portals}
      </div>
    );
  }),
);
