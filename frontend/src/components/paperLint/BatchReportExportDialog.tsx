import {useEffect, useRef, useState} from 'react';
import {Archive, Check, Download, LoaderCircle} from 'lucide-react';
import type {PaperLintReportListItem} from '../../api/paperLint';
import {getLocale} from '../../i18n/locale';
import {preserveText} from '../../i18n/jsx-runtime';
import {createBatchReportFile} from '../../utils/reportExport/batch';
import {downloadReportFile, type ReportExportFormat} from '../../utils/reportExport/formats';
import {Button} from '../shadcn/button';
import {Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger} from '../shadcn/dialog';
import {REPORT_EXPORT_FORMATS} from './reportExportFormats';

type Props = {reports: PaperLintReportListItem[]; disabled?: boolean; onBusyChange: (busy: boolean) => void};
export function BatchReportExportDialog({reports, disabled, onBusyChange}: Props) {
  const [open, setOpen] = useState(false), [pending, setPending] = useState<ReportExportFormat | null>(null);
  const [completed, setCompleted] = useState(0), [error, setError] = useState<string | null>(null), [success, setSuccess] = useState<string | null>(null);
  const active = useRef<AbortController | null>(null);
  useEffect(() => () => {active.current?.abort();}, []);
  async function download(format: ReportExportFormat) {
    if (active.current || !reports.length) return;
    const ids = reports.map(report => report.id), locale = getLocale() === 'en' ? 'en' : 'zh';
    const controller = new AbortController();
    active.current = controller;
    setPending(format); setCompleted(0); setError(null); setSuccess(null); onBusyChange(true);
    try {
      const file = await createBatchReportFile(ids, format, {locale, signal: controller.signal,
        onProgress: value => {if (active.current === controller) setCompleted(value.completed);}});
      if (controller.signal.aborted) return;
      downloadReportFile(file);
      setSuccess(`已打包 ${ids.length} 份报告`);
    } catch (cause) {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : '报告导出失败，请稍后重试。');
    } finally {
      if (active.current === controller) {active.current = null; setPending(null); onBusyChange(false);}
    }
  }
  function cancel() {
    active.current?.abort(); active.current = null;
    setPending(null); setSuccess('已取消导出'); onBusyChange(false);
  }
  return <Dialog open={open} onOpenChange={next => {
    if (active.current && !next) return;
    setOpen(next); setError(null); setSuccess(null);
  }}>
    <DialogTrigger asChild><Button size="sm" disabled={disabled || !reports.length}>
      <Download className="size-3.5"/>导出选中（{reports.length}）
    </Button></DialogTrigger>
    <DialogContent data-i18n-export="" className="top-[50dvh] left-[50vw] max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-xl"
      onEscapeKeyDown={event => {if (active.current) event.preventDefault();}}
      onPointerDownOutside={event => {if (active.current) event.preventDefault();}}>
      <DialogHeader><DialogTitle>批量导出报告</DialogTitle>
        <DialogDescription>选择导出格式，所有选中报告将打包为一个 ZIP 文件。</DialogDescription></DialogHeader>
      <div className="flex items-center gap-3 rounded-xl border border-brand-100 bg-brand-50/60 px-4 py-3">
        <Archive aria-hidden="true" className="size-5 shrink-0 text-brand-600"/>
        <p className="text-sm font-medium text-slate-700">已选择 {reports.length} 份报告</p>
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">{REPORT_EXPORT_FORMATS.map(({id,label,icon:Icon,color}) =>
        <button key={id} type="button" disabled={Boolean(pending)} onClick={() => void download(id)} aria-label={`导出 ${label}`}
          className="flex min-h-24 flex-col items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-4 text-sm font-semibold text-slate-800 transition-colors hover:border-brand-300 hover:bg-brand-50/40 focus-visible:outline-2 focus-visible:outline-brand-500 disabled:cursor-wait disabled:opacity-50">
          <span className={`flex size-9 items-center justify-center rounded-lg ${color}`}>{pending === id ? <LoaderCircle className="size-5 animate-spin"/> : <Icon className="size-5"/>}</span>{label}
        </button>)}</div>
      {pending ? <div className="rounded-xl border border-brand-100 bg-brand-50/60 px-3 py-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p role="status" className="flex items-center gap-2 text-sm text-brand-700"><LoaderCircle className="size-4 animate-spin"/>{`正在打包报告：${completed} / ${reports.length}`}</p>
          <Button type="button" size="sm" variant="ghost" onClick={cancel}>取消导出</Button>
        </div>
        <progress aria-label="报告导出进度" value={completed} max={reports.length} className="mt-2 h-1.5 w-full accent-brand-600"/>
      </div> : null}
      {error ? <p role="alert" className="rounded-lg bg-red-50 px-3 py-2.5 text-sm leading-6 text-red-700">{preserveText(error)}</p> : null}
      {success ? <p role="status" className="flex items-center gap-2 rounded-lg bg-emerald-50 px-3 py-2.5 text-sm text-emerald-700"><Check className="size-4"/>{success}</p> : null}
    </DialogContent>
  </Dialog>;
}
