import {Zip, ZipPassThrough} from 'fflate';
import {fetchPaperLintReport, fetchPaperLintDocumentMetrics, fetchReviewPilotPaperLintRules} from '../../api/paperLint';
import {fetchPaperLintRepairSuggestionHistory, type RepairSuggestion} from '../../api/repairSuggestions';
import {getLocale} from '../../i18n/locale';
import {buildExportReport} from './model';
import {createReportFile, type ExportFile, type ReportExportFormat} from './formats';
import {checkCancelled} from './renderPages';

type Options = {
  locale?: 'zh' | 'en';
  signal?: AbortSignal;
  onProgress?: (progress: {completed: number; total: number}) => void;
};
const MAX_ARCHIVE_BYTES = 128 * 1024 * 1024;

export async function createBatchReportFile(ids: string[], format: ReportExportFormat, options: Options = {}): Promise<ExportFile> {
  const {signal, onProgress} = options;
  const locale: 'zh' | 'en' = options.locale ?? (getLocale() === 'en' ? 'en' : 'zh');
  checkCancelled(signal, locale);
  const selected = [...new Set(ids)];
  if (!selected.length) throw new Error(locale === 'en' ? 'Select reports to export.' : '请先选择要导出的报告。');
  onProgress?.({completed: 0, total: selected.length});
  const {rules} = await fetchReviewPilotPaperLintRules();
  checkCancelled(signal, locale);
  const chunks: ArrayBuffer[] = [];
  let totalBytes = 0, zipError: Error | null = null;
  const zip = new Zip((error, chunk) => {
    if (error) zipError = error;
    else chunks.push(new Uint8Array(chunk).buffer);
  });
  try {
    for (const [index, id] of selected.entries()) {
      checkCancelled(signal, locale);
      let filename = String(index + 1);
      try {
        // Read saved content only. Rendering uses the same authenticated single-report export.
        const [report, metrics, saved] = await Promise.all([
          fetchPaperLintReport(id),
          fetchPaperLintDocumentMetrics(id).catch(() => null),
          fetchPaperLintRepairSuggestionHistory(id),
        ]);
        checkCancelled(signal, locale);
        filename = report.source_filename;
        if (report.id !== id) throw new Error(locale === 'en' ? 'The saved report does not match the selection.' : '报告与所选记录不匹配。');
        const repairs: Record<string, RepairSuggestion> = {};
        for (const item of saved) {
          if (!repairs[item.finding_id] || item.generation >= (repairs[item.finding_id].generation ?? 0))
            repairs[item.finding_id] = {...item.response, generation: item.generation};
        }
        const file = await createReportFile(buildExportReport(report, rules, metrics, repairs), format, {signal, locale});
        checkCancelled(signal, locale);
        totalBytes += file.blob.size;
        if (totalBytes > MAX_ARCHIVE_BYTES) throw new Error(locale === 'en'
          ? 'The archive exceeds 128 MB. Select fewer reports and export in batches.'
          : '压缩包内容超过 128 MB，请减少选择并分批导出。');
        const contents = new Uint8Array(await file.blob.arrayBuffer());
        checkCancelled(signal, locale);
        const entryName = `${String(index + 1).padStart(3, '0')}_${file.filename.replace(/[\\/\u0000]/g, '_')}`;
        const entry = new ZipPassThrough(entryName);
        zip.add(entry);
        entry.push(contents, true);
        if (zipError) throw zipError;
        onProgress?.({completed: index + 1, total: selected.length});
        // Let the browser paint progress and handle cancellation between files.
        await new Promise<void>(resolve => setTimeout(resolve, 0));
      } catch (cause) {
        checkCancelled(signal, locale);
        const reason = cause instanceof Error ? cause.message : String(cause);
        throw new Error(locale === 'en' ? `Could not export “${filename}”: ${reason}` : `无法导出“${filename}”：${reason}`);
      }
    }
    checkCancelled(signal, locale);
    zip.end();
    if (zipError) throw zipError;
    return {filename: locale === 'en' ? `Reports_${selected.length}.zip` : `检测报告_${selected.length}份.zip`, blob: new Blob(chunks, {type: 'application/zip'})};
  } finally {
    zip.terminate();
  }
}
