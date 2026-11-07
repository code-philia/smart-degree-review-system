import { ChevronDown, ListChecks } from 'lucide-react';
import type { PaperLintRule, PaperLintRunResponse } from '../../api/paperLint';
import { buildDetectionScope } from '../../utils/reportExport/model';
import { isDocumentBlocked } from './model';

export function DetectionScope({ report, rules }: { report: PaperLintRunResponse; rules: PaperLintRule[] }) {
  if (isDocumentBlocked(report.result.rule_runs)) return <p role="status" className="rounded-xl border border-red-100 bg-red-50 p-4 text-sm text-red-800">论文编译校验未通过，所选 {report.selected_rule_ids?.length ?? 0} 条论文规则全部未执行。</p>;
  const scope = buildDetectionScope(report, rules);
  const automaticCount = report.result.rule_runs.filter(run => run.params?.automatic_core_check === true
    && !report.selected_rule_ids?.includes(run.rule_id)).length;
  return (
    <details className="group overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <summary className="flex cursor-pointer list-none flex-wrap items-center gap-3 px-5 py-4 transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-500 [&::-webkit-details-marker]:hidden">
        <ListChecks aria-hidden="true" className="size-4 shrink-0 text-brand-700" />
        <span className="text-sm font-semibold text-slate-900">本次检测范围</span>
        <span className="text-xs text-slate-500">已选择 {scope.length - automaticCount} 项规则{automaticCount ? ` · 自动检查 ${automaticCount} 项` : ''}</span>
        <ChevronDown aria-hidden="true" className="ml-auto size-4 shrink-0 text-slate-400 transition-transform group-open:rotate-180" />
      </summary>
      <div className="border-t border-slate-100 px-5 py-4">
        {scope.length ? (
          <ol className="grid gap-x-6 gap-y-4 md:grid-cols-2">
            {scope.map((rule) => (
              <li key={rule.id} className="min-w-0 border-l-2 border-slate-200 pl-3">
                <p className="text-sm font-medium text-slate-800">{rule.title}</p>
                <p className="mt-1 text-xs leading-5 text-slate-500">{rule.description}</p>
              </li>
            ))}
          </ol>
        ) : <p className="text-sm text-slate-500">未记录检测规则，无法确认本次检测范围。</p>}
      </div>
    </details>
  );
}
