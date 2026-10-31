import { ChevronDown, ListChecks } from 'lucide-react';
import type { PaperLintRule, PaperLintRunResponse } from '../../api/paperLint';
import { buildDetectionScope } from '../../utils/reportExport/model';

export function DetectionScope({ report, rules }: { report: PaperLintRunResponse; rules: PaperLintRule[] }) {
  const scope = buildDetectionScope(report, rules);
  return (
    <details className="group overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <summary className="flex cursor-pointer list-none flex-wrap items-center gap-3 px-5 py-4 transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-500 [&::-webkit-details-marker]:hidden">
        <ListChecks aria-hidden="true" className="size-4 shrink-0 text-brand-700" />
        <span className="text-sm font-semibold text-slate-900">本次检测范围</span>
        <span className="text-xs text-slate-500">已选择 {scope.length} 项规则</span>
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
