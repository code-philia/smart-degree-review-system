import { LoaderCircle, Square } from 'lucide-react';
import { useMemo } from 'react';
import type { PaperLintRule, PaperLintRuleRun } from '../../api/paperLint';
import { Button, StatusBadge } from '../ui';
import { flattenPaperLintFindings } from './model';
import { PaperLintWorkspace } from './Workspace';

type Props = {
  file: File | { name: string; url: string };
  rules: PaperLintRule[];
  runs: PaperLintRuleRun[];
  progress: { completed: number; total: number } | null;
  stopping: boolean;
  onStop: () => void;
  error: string | null;
};

export function LivePaperLintReport({ file, rules, runs, progress, stopping, onStop, error }: Props) {
  const findings = useMemo(() => flattenPaperLintFindings({ rule_runs: runs }), [runs]);
  const numericRun = runs.find(run => run.rule_id === 'abstract_numeric_consistency_check');
  const completed = progress?.completed || 0;
  const total = progress?.total || 0;
  const percent = total ? Math.round(Math.min(1, completed / total) * 100) : undefined;
  const failed = runs.filter(run => run.execution_status === 'error');
  const undecided = runs.filter(run => run.execution_status === 'unsupported' || run.outcome === 'inconclusive');
  return (
    <section aria-label="实时检测报告" className="mx-auto w-full max-w-[1600px] space-y-5">
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <p className="text-xs font-semibold text-brand-700">实时检测报告</p>
            <h1 className="mt-2 break-all text-lg font-bold text-slate-900 sm:text-xl">{file.name}</h1>
            <p role="status" className="mt-2 text-xs leading-6 text-slate-500">检测进行中，新发现的问题将自动更新到报告中。完成后自动保存至历史报告。</p>
          </div>
          <Button variant="ghost" disabled={stopping} onClick={onStop}>
            {stopping ? <LoaderCircle className="size-4 animate-spin" /> : <Square className="size-3.5" />}
            {stopping ? '正在停止…' : '停止检测'}
          </Button>
        </div>
        <div className="mt-5 flex items-center justify-between gap-3 text-xs text-slate-500">
          <span>{total && completed >= total ? `已完成 ${completed} / ${total} 项规则，正在保存报告。` : `已完成 ${completed} / ${total || '—'} 项规则`}</span>
          <div className="flex items-center gap-3">{percent !== undefined ? <span className="tabular-nums">{percent}%</span> : null}<StatusBadge tone="info">检测进行中</StatusBadge></div>
        </div>
        <div role="progressbar" aria-label="检测进度" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}
          aria-valuetext={total ? `规则完成进度，${completed} / ${total} 项，${percent}%` : '开始解析'}
          className="mt-2 h-1.5 overflow-hidden rounded-full bg-brand-100">
          <div className="h-full rounded-full bg-brand-600 transition-[width] duration-300 motion-reduce:transition-none" style={{ width: `${percent || 0}%` }} />
        </div>
        <h2 className="mt-5 text-sm font-bold text-slate-900">检测结论</h2>
        <dl className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-4" aria-live="polite" aria-atomic="true">
          {[
            ['错误总数', findings.length],
            ['严重错误数', findings.filter(item => item.ruleRun.severity === 'error').length],
            ['警告错误数', findings.filter(item => item.ruleRun.severity === 'warning').length],
            ['提示错误数', findings.filter(item => item.ruleRun.severity === 'info').length],
          ].map(([label, count]) => <div key={label} className="rounded-xl border border-slate-100 bg-slate-50/70 p-3">
            <dt className="text-xs text-slate-500">{label}</dt><dd className="mt-1 text-2xl font-bold tabular-nums text-slate-900">{count}</dd>
          </div>)}
        </dl>
        {failed.length || undecided.length ? <p className="mt-3 text-xs leading-6 text-amber-800">{failed.length ? `${failed.length} 项规则执行失败。` : ''}{undecided.length ? `${undecided.length} 项规则暂无法判定。` : ''}{[...new Set([...failed, ...undecided].map(run => run.message).filter(Boolean))].join('；')}</p> : null}
      </div>
      {error ? <p role="alert" className="rounded-xl bg-red-50 p-4 text-sm text-red-700">{error}</p> : null}
      <PaperLintWorkspace file={file} findings={findings} rules={rules} numericReviewRun={numericRun} running />
    </section>
  );
}
