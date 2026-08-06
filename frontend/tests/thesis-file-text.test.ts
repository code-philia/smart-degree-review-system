import { beforeEach, describe, expect, it, vi } from 'vitest';
import { extractThesisFileText } from '../src/utils/thesisFileText';

const mocks = vi.hoisted(() => ({
  destroy: vi.fn(),
  getDocument: vi.fn(),
}));

vi.mock('pdfjs-dist', () => ({
  GlobalWorkerOptions: { workerSrc: '' },
  getDocument: mocks.getDocument,
}));

vi.mock('pdfjs-dist/build/pdf.worker.min.mjs?url', () => ({
  default: '/assets/pdf.worker.min.mjs',
}));

describe('searchable PDF text extraction', () => {
  beforeEach(() => {
    mocks.destroy.mockReset().mockResolvedValue(undefined);
    mocks.getDocument.mockReset();
  });

  it('extracts searchable text page by page and preserves line and page breaks', async () => {
    const getPage = vi.fn(async (pageNumber: number) => ({
      getTextContent: async () => ({
        items:
          pageNumber === 1
            ? [
                { str: '摘要', hasEOL: true },
                { str: '研究内容', hasEOL: false },
              ]
            : [{ str: '结论', hasEOL: false }],
      }),
    }));
    mocks.getDocument.mockReturnValue({
      destroy: mocks.destroy,
      promise: Promise.resolve({ getPage, numPages: 2 }),
    });
    const progress = vi.fn();

    await expect(
      extractThesisFileText(new File(['%PDF-1.7'], '论文.pdf', { type: 'application/pdf' }), progress),
    ).resolves.toEqual({ text: '摘要\n研究内容\n\n结论', pageCount: 2 });
    expect(progress).toHaveBeenNthCalledWith(1, { currentPage: 1, totalPages: 2 });
    expect(progress).toHaveBeenNthCalledWith(2, { currentPage: 2, totalPages: 2 });
    expect(mocks.destroy).toHaveBeenCalledOnce();
  });

  it('rejects a PDF without a searchable text layer', async () => {
    mocks.getDocument.mockReturnValue({
      destroy: mocks.destroy,
      promise: Promise.resolve({
        getPage: async () => ({ getTextContent: async () => ({ items: [] }) }),
        numPages: 1,
      }),
    });

    await expect(
      extractThesisFileText(new File(['%PDF-1.7'], '扫描件.pdf', { type: 'application/pdf' })),
    ).rejects.toThrow('未从 PDF 中提取到文字，该文件可能是扫描版 PDF');
    expect(mocks.destroy).toHaveBeenCalledOnce();
  });
});
