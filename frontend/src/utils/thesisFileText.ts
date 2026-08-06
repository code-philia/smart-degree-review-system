const MAX_TEXT_FILE_BYTES = 5 * 1024 * 1024;
const MAX_PDF_FILE_BYTES = 50 * 1024 * 1024;
const MAX_EXTRACTED_TEXT_BYTES = 5 * 1024 * 1024;
const MAX_PDF_PAGES = 500;

export const THESIS_FILE_ACCEPT = '.txt,.md,.pdf,text/plain,text/markdown,application/pdf';

export type ThesisFileExtractionProgress = {
  currentPage: number;
  totalPages: number;
};

export type ThesisFileText = {
  text: string;
  pageCount: number | null;
};

function getFileExtension(fileName: string) {
  const dotIndex = fileName.lastIndexOf('.');
  return dotIndex === -1 ? '' : fileName.slice(dotIndex).toLowerCase();
}

function readBinaryFile(file: File): Promise<ArrayBuffer> {
  if (typeof file.arrayBuffer === 'function') {
    return file.arrayBuffer();
  }

  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      if (reader.result instanceof ArrayBuffer) {
        resolve(reader.result);
        return;
      }
      reject(new Error('PDF 文件读取失败'));
    };
    reader.onerror = () => reject(reader.error || new Error('PDF 文件读取失败'));
    reader.readAsArrayBuffer(file);
  });
}

async function readUtf8TextFile(file: File) {
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(await readBinaryFile(file));
  } catch {
    throw new Error('文本文件必须使用 UTF-8 编码');
  }
}

function assertTextSize(text: string) {
  if (new TextEncoder().encode(text).byteLength > MAX_EXTRACTED_TEXT_BYTES) {
    throw new Error('文件提取后的文本不能超过 5 MB');
  }
}

function normalizePdfError(error: unknown): Error {
  const errorName = error && typeof error === 'object' && 'name' in error ? String(error.name) : '';

  if (errorName === 'PasswordException') {
    return new Error('暂不支持加密或需要密码的 PDF');
  }
  if (errorName === 'InvalidPDFException') {
    return new Error('PDF 文件无效或已经损坏');
  }
  if (error instanceof Error) {
    return error;
  }
  return new Error('PDF 文件解析失败');
}

async function extractPdfText(
  file: File,
  onProgress?: (progress: ThesisFileExtractionProgress) => void,
): Promise<ThesisFileText> {
  const [{ getDocument, GlobalWorkerOptions }, workerModule] = await Promise.all([
    import('pdfjs-dist'),
    import('pdfjs-dist/build/pdf.worker.min.mjs?url'),
  ]);
  GlobalWorkerOptions.workerSrc = workerModule.default;

  const data = new Uint8Array(await readBinaryFile(file));
  const loadingTask = getDocument({ data });

  try {
    const document = await loadingTask.promise;
    if (document.numPages > MAX_PDF_PAGES) {
      throw new Error(`PDF 页数不能超过 ${MAX_PDF_PAGES} 页`);
    }

    const pageTexts: string[] = [];
    for (let pageNumber = 1; pageNumber <= document.numPages; pageNumber += 1) {
      onProgress?.({ currentPage: pageNumber, totalPages: document.numPages });
      const page = await document.getPage(pageNumber);
      const content = await page.getTextContent();
      let pageText = '';

      for (const item of content.items) {
        if (!('str' in item)) {
          continue;
        }
        pageText += item.str;
        if (item.hasEOL) {
          pageText += '\n';
        }
      }

      pageTexts.push(pageText.trim());
      assertTextSize(pageTexts.join('\n\n'));
    }

    const text = pageTexts.join('\n\n').trim();
    if (!text) {
      throw new Error('未从 PDF 中提取到文字，该文件可能是扫描版 PDF');
    }

    return { text, pageCount: document.numPages };
  } catch (error) {
    throw normalizePdfError(error);
  } finally {
    await loadingTask.destroy().catch(() => undefined);
  }
}

export async function extractThesisFileText(
  file: File,
  onProgress?: (progress: ThesisFileExtractionProgress) => void,
): Promise<ThesisFileText> {
  const extension = getFileExtension(file.name);
  if (extension === '.txt' || extension === '.md') {
    if (file.size > MAX_TEXT_FILE_BYTES) {
      throw new Error('文本文件大小不能超过 5 MB');
    }
    const text = await readUtf8TextFile(file);
    assertTextSize(text);
    return { text, pageCount: null };
  }
  if (extension === '.pdf') {
    if (file.size > MAX_PDF_FILE_BYTES) {
      throw new Error('PDF 文件大小不能超过 50 MB');
    }
    return extractPdfText(file, onProgress);
  }

  throw new Error('仅支持上传 .txt、.md 或 .pdf 文件');
}
