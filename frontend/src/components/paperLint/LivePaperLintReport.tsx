import { useMemo } from 'react';
import type { PaperLintRule, PaperLintRuleRun } from '../../api/paperLint';
import { StatusBadge } from '../ui';
import { documentCheckId, isDocumentBlocked, flattenPaperLintFindings, numericExecutionWarnings, genericExecutionWarnings, referenceResourcesUnavailable, referencePresentationRun } from './model';
import { PaperLintWorkspace } from './Workspace';
import { REPORT_DOCUMENT_TEXT } from './documentTypography';

type Props = {
  file: File | { name: string; url: string };
  rules: PaperLintRule[];
  runs: PaperLintRuleRun[];
  selectedRuleIds?: string[];
};

export function LivePaperLintReport({ file, rules, runs, selectedRuleIds }: Props) {
  const reportRuns = useMemo(() => runs.map(referencePresentationRun), [runs]);
  const findings = useMemo(() => flattenPaperLintFindings({ rule_runs: reportRuns }), [reportRuns]);
  const numericRun = runs.find(run => run.rule_id === 'abstract_numeric_consistency_check');
  const documentBlocked = isDocumentBlocked(reportRuns);
  const executionWarningCount = numericExecutionWarnings(numericRun).length + genericExecutionWarnings(reportRuns).length;
  const issueTotal = findings.length + executionWarningCount;
  const failed = reportRuns.filter(run => run.execution_status === 'error');
  const undecided = reportRuns.filter(run => run.execution_status !== 'error'
    && !(run.rule_id === 'sjtu_rule_32' && run.execution_status === 'completed' && !referenceResourcesUnavailable(run))
    && (run.execution_status === 'unsupported' || run.outcome === 'inconclusive'));
  return (
    <section aria-label="实时检测报告" className="mx-auto w-full max-w-[1600px] space-y-5">
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <p className="text-lg font-bold leading-7 tracking-tight text-brand-700 sm:text-xl">实时检测报告</p>
            <h2 className={`mt-1 break-all text-slate-600 ${REPORT_DOCUMENT_TEXT}`}>{file.name}</h2>
          </div>
          <StatusBadge tone="info">实时更新</StatusBadge>
        </div>
        <h3 className="mt-5 text-sm font-bold text-slate-900">检测结论</h3>
        <dl className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5" aria-live="polite" aria-atomic="true">
          {[
            ['错误总数', issueTotal],
            ['严重错误数', findings.filter(item => item.ruleRun.severity === 'error').length],
            ['警告错误数', findings.filter(item => item.ruleRun.severity === 'warning').length],
            ['提示错误数', findings.filter(item => item.ruleRun.severity === 'info').length],
            ['规则未实现警告数', executionWarningCount],
          ].map(([label, count]) => <div key={label} className={`rounded-xl border p-3 ${label === '规则未实现警告数' ? 'border-violet-100 bg-violet-50/50' : 'border-slate-100 bg-slate-50/70'}`}>
            <dt className={`text-xs ${label === '规则未实现警告数' ? 'text-violet-700' : 'text-slate-500'}`}>{label}</dt><dd className={`mt-1 text-2xl font-bold tabular-nums ${label === '规则未实现警告数' ? 'text-violet-700' : 'text-slate-900'}`}>{count}</dd>
          </div>)}
        </dl>
        <p role="status" className="mt-3 h-12 overflow-y-auto text-xs leading-6 text-slate-500">
          {documentBlocked ? '论文编译校验未通过，所有论文规则均未检测。请查看严重级别的具体原因。' : failed.length || undecided.length
            ? `${failed.length ? `${failed.length} 项规则执行失败。` : ''}${undecided.length ? `${undecided.length} 项规则暂无法判定。` : ''}`
            : '检测进行中，新发现的问题将自动更新到报告中。完成后自动保存至历史报告。'}
        </p>
      </div>
      <PaperLintWorkspace file={file} findings={findings} rules={rules} selectedRuleIds={documentBlocked ? [documentCheckId] : selectedRuleIds} ruleRuns={reportRuns} numericReviewRun={numericRun} running={!documentBlocked} />
    </section>
  );
}
