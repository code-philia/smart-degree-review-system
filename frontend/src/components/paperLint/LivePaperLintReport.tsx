import { useMemo } from 'react';
import type { PaperLintRule, PaperLintRuleRun } from '../../api/paperLint';
import { StatusBadge } from '../ui';
import { flattenPaperLintFindings } from './model';
import { PaperLintWorkspace } from './Workspace';

type Props = {
  file: File | { name: string; url: string };
  rules: PaperLintRule[];
  runs: PaperLintRuleRun[];
};

export function LivePaperLintReport({ file, rules, runs }: Props) {
  const findings = useMemo(() => flattenPaperLintFindings({ rule_runs: runs }), [runs]);
  const numericRun = runs.find(run => run.rule_id === 'abstract_numeric_consistency_check');
  const failed = runs.filter(run => run.execution_status === 'error');
  const undecided = runs.filter(run => run.execution_status === 'unsupported' || run.outcome === 'inconclusive');
  return (
    <section aria-label="实时检测报告" className="mx-auto w-full max-w-[1600px] space-y-5">
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <p className="text-xs font-semibold text-brand-700">实时检测报告</p>
            <h2 className="mt-2 break-all text-lg font-bold text-slate-900 sm:text-xl">{file.name}</h2>
          </div>
          <StatusBadge tone="info">实时更新</StatusBadge>
        </div>
        <h3 className="mt-5 text-sm font-bold text-slate-900">检测结论</h3>
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
        <p role="status" className="mt-3 h-12 overflow-y-auto text-xs leading-6 text-slate-500">
          {failed.length || undecided.length
            ? `${failed.length ? `${failed.length} 项规则执行失败。` : ''}${undecided.length ? `${undecided.length} 项规则暂无法判定。` : ''}${[...new Set([...failed, ...undecided].map(run => run.message).filter(Boolean))].join('；')}`
            : '检测进行中，新发现的问题将自动更新到报告中。完成后自动保存至历史报告。'}
        </p>
      </div>
      <PaperLintWorkspace file={file} findings={findings} rules={rules} numericReviewRun={numericRun} running />
    </section>
  );
}
