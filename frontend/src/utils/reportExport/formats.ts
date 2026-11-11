import apiClient from '../../api';
import { createTranslator, getLocale } from '../../i18n/locale.js';
import { ensureReportTranslations, assertTranslationsReady } from '../../i18n/reportTranslations';
import { collectExportTranslationTexts, localizeExportReport, reportLocale } from './presentation';
import { reportMarkdown, reportText, safeReportFilename, type ExportReportBundle, type ExportReport } from './model';
import { checkCancelled, type ExportProgress } from './renderPages';

export type ReportExportFormat = 'pdf' | 'markdown' | 'text' | 'docx' | 'image' | 'json';
export type ExportFile = { blob: Blob; filename: string };
type Options = { signal?: AbortSignal; onProgress?: ExportProgress; locale?: 'zh' | 'en' };

const exportErrors: Record<string, string> = {
  '导出报告内容无效，请刷新报告后重试。': 'The report export content is invalid. Refresh the report and try again.',
  '报告内容过大，请联系系统管理员。': 'The report content is too large. Contact the system administrator.',
  '报告正在导出，请稍后重试。': 'This report is already being exported. Try again shortly.',
  '报告导出超时，请稍后重试。': 'The report export timed out. Try again shortly.',
  '报告导出暂不可用，请稍后重试。': 'Report export is temporarily unavailable. Try again shortly.',
  '导出文件过大，请联系系统管理员。': 'The exported file is too large. Contact the system administrator.',
};
async function exportFailure(error: unknown, locale: string): Promise<Error> {
  const failure = error as { message?: string; code?: string; response?: { status?: number; data?: unknown } };
  let message = failure?.message || '';
  const data = failure?.response?.data;
  try {
    const body = data instanceof Blob && data.size < 20000 ? JSON.parse(await data.text()) : data;
    if (body && typeof body === 'object' && 'message' in body && typeof body.message === 'string')
      message = body.message;
  } catch {
    /* Use the HTTP status if a proxy did not return JSON. */
  }
  const status = failure?.response?.status;
  const fallback: Record<number, [string, string]> = {
    400: ['导出报告内容无效，请刷新报告后重试。', exportErrors['导出报告内容无效，请刷新报告后重试。']],
    401: ['请重新登录后导出报告。', 'Sign in again before exporting the report.'],
    403: ['无权导出此报告。', 'You do not have permission to export this report.'],
    404: ['未找到已保存的报告。', 'The saved report could not be found.'],
    413: ['报告内容过大，请联系系统管理员。', exportErrors['报告内容过大，请联系系统管理员。']],
    429: ['报告正在导出，请稍后重试。', exportErrors['报告正在导出，请稍后重试。']],
    503: ['报告导出暂不可用，请稍后重试。', exportErrors['报告导出暂不可用，请稍后重试。']],
    504: ['报告导出超时，请稍后重试。', exportErrors['报告导出超时，请稍后重试。']],
  };
  if (locale === 'en')
    return new Error(exportErrors[message] || fallback[status ?? 0]?.[1] || 'Report export failed. Try again shortly.');
  return new Error(message || fallback[status ?? 0]?.[0] || '报告导出失败，请稍后重试。');
}

export async function createReportFile(
  model: ExportReport,
  format: ReportExportFormat,
  { signal, onProgress, locale: requestedLocale }: Options = {},
): Promise<ExportFile> {
  const locale = requestedLocale ?? getLocale(),
    t = createTranslator(locale);
  checkCancelled(signal, locale);
  if (reportLocale(model) === 'en') throw new Error('Export requires the original saved Chinese report.');
  if (locale === 'en') {
    const required = collectExportTranslationTexts(model),
      coverage = createTranslator('en');
    if (required.some((text) => !coverage.has(text))) {
      onProgress?.('Preparing English translation…');
      await ensureReportTranslations({ reportId: model.report_id }, required, { locale: 'en', force: true });
      checkCancelled(signal, locale);
    }
    assertTranslationsReady(required, 'en');
  }
  // Capture the chosen edition and translation snapshot before rendering callbacks.
  const selected = locale === 'en' ? localizeExportReport(model, 'en', createTranslator('en')) : model;
  const bundle: ExportReportBundle = {
    schema_version: 1,
    reports: [selected],
  };
  const stem = safeReportFilename(model.document.filename, locale);
  if (format === 'markdown')
    return {
      filename: stem + '.md',
      blob: new Blob([reportMarkdown(selected)], {
        type: 'text/markdown;charset=utf-8',
      }),
    };
  if (format === 'text')
    return {
      filename: stem + '.txt',
      blob: new Blob(['\uFEFF', reportText(selected)], {
        type: 'text/plain;charset=utf-8',
      }),
    };
  if (format === 'json')
    return {
      filename: stem + '.json',
      blob: new Blob([JSON.stringify(bundle, null, 2)], { type: 'application/json;charset=utf-8' }),
    };
  if (format === 'docx') {
    onProgress?.(t('正在生成可编辑 Word 文档'));
    const { createWordReport } = await import('./docxReport');
    checkCancelled(signal, locale);
    const blob = await createWordReport(selected);
    checkCancelled(signal, locale);
    return { filename: stem + '.docx', blob };
  }
  if (format === 'pdf' || format === 'image') {
    onProgress?.(t(format === 'pdf' ? '正在准备 PDF' : '正在打包全部报告图片'));
    let response;
    try {
      response = await apiClient.post<Blob>(
        `/normative/paper-lint/reports/${encodeURIComponent(model.report_id)}/export`,
        { format, model: bundle },
        { responseType: 'blob', timeout: 300000, signal },
      );
    } catch (error) {
      checkCancelled(signal, locale);
      throw await exportFailure(error, locale);
    }
    checkCancelled(signal, locale);
    const contentType = String(response.headers?.['content-type'] || response.data.type || '');
    const extension =
      format === 'pdf'
        ? '.pdf'
        : contentType.includes('image/png')
          ? '.png'
          : locale === 'en'
            ? '_Images.zip'
            : '_图片.zip';
    return { filename: stem + extension, blob: response.data };
  }
  throw new Error(t('暂不支持此导出格式'));
}

export function downloadReportFile({ blob, filename }: ExportFile) {
  const url = URL.createObjectURL(blob),
    anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.hidden = true;
  document.body.appendChild(anchor);
  try {
    anchor.click();
  } finally {
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}
