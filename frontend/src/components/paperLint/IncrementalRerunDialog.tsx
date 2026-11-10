import { preserveText } from "../../i18n/jsx-runtime";
import { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { RotateCw, LoaderCircle } from 'lucide-react';
import { rerunPaperLintReport, type PaperLintRule, type PaperLintRunResponse } from '../../api/paperLint';
import { Button } from '../shadcn/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '../shadcn/dialog';
import { REVIEW_ROUTES } from '../../nav/reviewRoutes';

type Props = { report: PaperLintRunResponse; rules: PaperLintRule[]; initiallyOpen?: boolean };
export function IncrementalRerunDialog({ report, rules, initiallyOpen = false }: Props) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(initiallyOpen);
  const [extraIds, setExtraIds] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestId = useRef<string | null>(null);
  const names = new Map(rules.map(rule => [rule.rule_id, rule.title]));
  const successful = new Set(report.result.rule_runs.filter(run => run.execution_status === 'completed' && run.outcome !== 'inconclusive').map(run => run.rule_id));
  const retryIds = report.selected_rule_ids.filter(id => !successful.has(id));
  const available = rules.filter(rule => rule.available && !report.selected_rule_ids.includes(rule.rule_id));
  const count = retryIds.length + extraIds.length;
  async function submit() {
    if (!count || submitting) return;
    setSubmitting(true); setError(null);
    requestId.current ||= typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID() : `rerun-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    try {
      const job = await rerunPaperLintReport(report.id, extraIds, requestId.current);
      if (!job.user_id) throw new Error('任务已提交，请从论文上传页恢复查看');
      localStorage.setItem(`paper-lint-active-job:${job.user_id}`, JSON.stringify({
        jobId: job.job_id, requestId: requestId.current, filename: job.source_filename || report.source_filename,
        selectedRuleIds: job.selected_rule_ids || [...report.selected_rule_ids, ...extraIds],
      }));
      navigate(REVIEW_ROUTES.upload);
    } catch (cause) { setError(cause instanceof Error ? cause.message : '增量补跑提交失败，请重试'); }
    finally { setSubmitting(false); }
  }
  return <Dialog open={open} onOpenChange={next => { if (!submitting) setOpen(next); }}>
    <DialogTrigger asChild><Button variant="outline" size="sm"><RotateCw className="size-4" />增量补跑</Button></DialogTrigger>
    <DialogContent data-i18n-rerun="" className="top-[50dvh] left-[50vw] max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-xl">
      <DialogHeader><DialogTitle>基于历史报告增量补跑</DialogTitle><DialogDescription>
        复用原 PDF 和已完成结果，只补跑新增、失败或未能判定的规则。生成新报告，原报告保持不变。
      </DialogDescription></DialogHeader>
      <p className="break-all rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-700">{preserveText(report.source_filename)}</p>
      <div className="max-h-80 space-y-2 overflow-y-auto">
        {report.selected_rule_ids.map(id => <div key={id} className="flex items-center justify-between gap-3 rounded-lg border border-slate-100 px-3 py-2 text-sm">
          <span>{names.get(id) || id}</span><span className={`shrink-0 text-xs font-medium ${successful.has(id) ? 'text-emerald-700' : 'text-amber-700'}`}>
            {successful.has(id) ? '复用已完成结果' : '本次补跑'}
          </span>
        </div>)}
        {available.map(rule => <label key={rule.rule_id} className="flex cursor-pointer items-start gap-3 rounded-lg border border-slate-200 px-3 py-3 text-sm hover:bg-slate-50">
          <input type="checkbox" className="mt-0.5 size-4 shrink-0 accent-brand-600" checked={extraIds.includes(rule.rule_id)} disabled={submitting}
            onChange={event => { setExtraIds(ids => event.target.checked ? [...ids, rule.rule_id] : ids.filter(id => id !== rule.rule_id)); requestId.current = null; }} />
          <span>{rule.title}<span className="ml-2 text-xs text-slate-400">新增规则</span></span>
        </label>)}
      </div>
      {!count ? <p className="text-xs leading-6 text-slate-500">已有规则均已完成，请勾选新增规则后补跑。</p> : null}
      {error ? <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p> : null}
      <Button disabled={!count || submitting} onClick={() => void submit()}>
        {submitting ? <LoaderCircle className="size-4 animate-spin" /> : <RotateCw className="size-4" />}
        {submitting ? '正在加入队列…' : `开始增量检测（${count} 项）`}
      </Button>
    </DialogContent>
  </Dialog>;
}
