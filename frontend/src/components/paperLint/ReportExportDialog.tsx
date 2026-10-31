import { useEffect, useRef, useState } from 'react';
import { Braces, Check, Download, FileImage, FileText, FileType2, FileDown, LoaderCircle } from 'lucide-react';
import type { PaperLintDocumentMetrics, PaperLintRule, PaperLintRunResponse } from '../../api/paperLint';
import { fetchPaperLintRepairSuggestionHistory, type RepairSuggestion } from '../../api/repairSuggestions';
import { Button } from '../shadcn/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '../shadcn/dialog';
import { buildExportReport } from '../../utils/reportExport/model';
import { createReportFile, downloadReportFile, type ReportExportFormat } from '../../utils/reportExport/formats';

const formats = [
  { id: 'pdf', label: 'PDF', icon: FileDown, color: 'text-rose-600 bg-rose-50' },
  {
    id: 'markdown',
    label: 'Markdown',
    icon: FileType2,
    color: 'text-indigo-600 bg-indigo-50',
  },
  { id: 'text', label: '文本', icon: FileText, color: 'text-amber-600 bg-amber-50' },
  {
    id: 'docx',
    label: 'Docx',
    icon: FileText,
    color: 'text-blue-600 bg-blue-50',
  },
  {
    id: 'image',
    label: '图片',
    icon: FileImage,
    color: 'text-emerald-600 bg-emerald-50',
  },
  { id: 'json', label: 'Json', icon: Braces, color: 'text-orange-600 bg-orange-50' },
] as const;

type Props = {
  report: PaperLintRunResponse;
  rules: PaperLintRule[];
  metrics: PaperLintDocumentMetrics | null;
  repairs?: Record<string, RepairSuggestion | undefined>;
};
export function ReportExportDialog({ report, rules, metrics, repairs = {} }: Props) {
  const [open, setOpen] = useState(false),
    [pending, setPending] = useState<ReportExportFormat | null>(null),
    [progress, setProgress] = useState(''),
    [error, setError] = useState<string | null>(null),
    [success, setSuccess] = useState<string | null>(null);
  const active = useRef<AbortController | null>(null);
  useEffect(
    () => () => {
      active.current?.abort();
      active.current = null;
    },
    [report.id],
  );
  async function download(format: ReportExportFormat) {
    if (active.current) return;
    const controller = new AbortController();
    active.current = controller;
    setPending(format);
    setProgress('正在准备报告内容');
    setError(null);
    setSuccess(null);
    try {
      // This authenticated read retrieves only saved suggestions; it never evaluates a rule/model.
      const saved = await fetchPaperLintRepairSuggestionHistory(report.id);
      if (controller.signal.aborted) return;
      const latest = { ...repairs };
      for (const item of saved) {
        const current = latest[item.finding_id];
        if (!current || (item.generation ?? 0) >= (current.generation ?? 0))
          latest[item.finding_id] = { ...item.response, generation: item.generation };
      }
      const model = buildExportReport(report, rules, metrics, latest);
      const file = await createReportFile(model, format, { signal: controller.signal, onProgress: setProgress });
      if (controller.signal.aborted) return;
      downloadReportFile(file);
      setSuccess(`已生成 ${file.filename}`);
    } catch (cause) {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : '报告导出失败，请稍后重试。');
    } finally {
      if (active.current === controller) {
        active.current = null;
        setPending(null);
        setProgress('');
      }
    }
  }
  function changeOpen(next: boolean) {
    if (pending && !next) return;
    setOpen(next);
    if (!next) {
      setError(null);
      setSuccess(null);
    }
  }
  function cancelDownload() {
    active.current?.abort();
    active.current = null;
    setPending(null);
    setProgress('');
    setSuccess(null);
  }
  return (
    <Dialog open={open} onOpenChange={changeOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <Download className="size-4" />
          下载检测报告
        </Button>
      </DialogTrigger>
      <DialogContent
        className="top-[50dvh] left-[50vw] max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-xl"
        onEscapeKeyDown={(event) => {
          if (pending) event.preventDefault();
        }}
        onPointerDownOutside={(event) => {
          if (pending) event.preventDefault();
        }}
      >
        <DialogHeader className="items-center pt-1 text-center">
          <DialogTitle className="text-lg font-semibold">导出检测报告</DialogTitle>
          <DialogDescription className="sr-only">选择检测报告的导出格式</DialogDescription>
        </DialogHeader>
        <div className="rounded-xl border border-slate-100 bg-slate-50/80 px-4 py-3">
          <p className="break-all text-center text-sm font-medium text-slate-800">{report.source_filename}</p>
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {formats.map(({ id, label, icon: Icon, color }) => (
            <button
              key={id}
              type="button"
              disabled={Boolean(pending)}
              onClick={() => void download(id)}
              className="group flex min-h-28 flex-col items-center justify-center gap-2 rounded-2xl border border-slate-200 bg-white px-3 py-4 text-center shadow-sm transition duration-200 hover:-translate-y-0.5 hover:border-blue-300 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 disabled:cursor-wait disabled:opacity-55 disabled:hover:translate-y-0"
              aria-label={`导出 ${label}`}
            >
              <span className={`flex size-10 items-center justify-center rounded-xl ${color}`}>
                {pending === id ? <LoaderCircle className="size-6 animate-spin" /> : <Icon className="size-6" />}
              </span>
              <span className="text-sm font-semibold text-slate-800">{label}</span>
            </button>
          ))}
        </div>
        {pending ? (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-blue-50 px-3 py-2">
            <p role="status" className="flex items-center gap-2 text-sm text-blue-700">
              <LoaderCircle className="size-4 animate-spin" />
              {progress}
            </p>
            <Button type="button" size="sm" variant="ghost" onClick={cancelDownload}>
              取消导出
            </Button>
          </div>
        ) : null}
        {error ? (
          <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">
            {error}
          </p>
        ) : null}
        {success ? (
          <p
            role="status"
            className="flex items-start gap-2 break-all rounded-lg bg-emerald-50 p-3 text-sm text-emerald-700"
          >
            <Check className="mt-0.5 size-4 shrink-0" />
            {success}
          </p>
        ) : null}
        <p className="text-right text-xs leading-5 text-slate-500">检测结果仅供参考，请结合论文原文人工复核。</p>
      </DialogContent>
    </Dialog>
  );
}
