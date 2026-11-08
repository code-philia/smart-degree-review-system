import { Select } from 'radix-ui';
import { Check, CheckCircle2, ChevronDown, ChevronUp, CircleAlert, CircleHelp, CircleX, FlaskConical, Funnel, Info, LoaderCircle, ShieldAlert, TriangleAlert } from 'lucide-react';

export type RuleSeverity = 'error' | 'warning' | 'info';
export type RuleFilterLevel = 'all' | RuleSeverity | 'execution';
export type RuleSeverityCounts = Record<RuleSeverity, number>;

export type RuleFilterOption = {
  id: string;
  title: string;
  count: number;
  counts: RuleSeverityCounts;
  status: 'running' | 'completed' | 'error' | 'needs_review' | 'not_applicable' | 'execution_warning';
  hasExecutionWarning?: boolean;
  executionWarningCount?: number;
};

export function isRuleVisible(option: RuleFilterOption, level: RuleFilterLevel) {
  if (level === 'all') return true;
  if (level === 'execution') return option.status === 'running' || warningCount(option) > 0;
  if (option.status === 'running') return true;
  if (option.counts[level] > 0) return true;
  return level === 'info' && !warningCount(option)
    && ['error', 'needs_review', 'not_applicable'].includes(option.status);
}

const labels = { running: '正在检测', error: '检测失败', needs_review: '待核查', not_applicable: '不适用', execution_warning: '规则未实现警告' };
const levels = ['error', 'warning', 'info'] as const;
const levelLabels = { error: '严重', warning: '警告', info: '提示' };

function ExperimentalBadge({ ruleId }: { ruleId: string }) {
  return ruleId === 'abstract_numeric_consistency_check'
    ? <span role="img" aria-label="实验性规则" title="实验性规则" className="inline-flex h-5 shrink-0 items-center gap-1 rounded-md bg-violet-50 px-1.5 text-[10px] font-medium leading-none text-violet-700"><FlaskConical aria-hidden="true" className="size-3" />实验性</span>
    : null;
}

function resultOrder(option: RuleFilterOption) {
  if (option.counts.error > 0) return 0;
  if (option.counts.warning > 0) return 1;
  if (warningCount(option) > 0 || option.status === 'error') return 2;
  if (option.counts.info > 0 || ['needs_review', 'not_applicable'].includes(option.status)) return 3;
  return option.status === 'running' ? 4 : 5;
}

function warningCount(option: RuleFilterOption) {
  return Math.max(option.executionWarningCount || 0, option.hasExecutionWarning || option.status === 'execution_warning' ? 1 : 0);
}

function showsWarningBadge(option: RuleFilterOption, severity: RuleFilterLevel) {
  return (severity === 'all' || severity === 'execution') && warningCount(option) > 0;
}

function statusLabel(option: RuleFilterOption, severity: RuleFilterLevel) {
  if (option.status === 'running') return labels.running;
  if (showsWarningBadge(option, severity)) return `${severity !== 'execution' && option.count ? `已发现 ${option.count} 处问题，` : ''}${option.status === 'error' ? '检测失败，' : ''}规则未实现警告`;
  if (severity === 'execution') return `${option.status === 'error' ? '检测失败，' : ''}规则未实现警告`;
  if (option.status === 'completed') return `问题总数 ${option.count} 处${levels.filter(level => (severity === 'all' || severity === level) && option.counts[level]).map(level => `，${levelLabels[level]} ${option.counts[level]} 处`).join('')}`;
  return `${option.count ? `已发现 ${option.count} 处问题，` : ''}${labels[option.status]}`;
}

type IncompleteStatus = 'error' | 'needs_review' | 'not_applicable' | 'running';
const incompleteStatuses: IncompleteStatus[] = ['error', 'needs_review', 'not_applicable', 'running'];

function hasStatusBadge(option: RuleFilterOption, status: IncompleteStatus, severity: RuleFilterLevel) {
  return option.status === status
    && !(showsWarningBadge(option, severity) && ['needs_review', 'not_applicable'].includes(status));
}

const countBadgeClassName = 'inline-flex min-w-10 shrink-0 items-center justify-center gap-1 rounded-full px-2.5 py-1.5 text-xs font-semibold tabular-nums';

function ExecutionStatus({ status, count }: { status: IncompleteStatus; count?: number }) {
  const Icon = status === 'running' ? LoaderCircle : status === 'error' ? CircleAlert : CircleHelp;
  const tone = status === 'running' ? 'bg-brand-50 text-brand-700' : status === 'error' ? 'bg-rose-50 text-rose-700' : status === 'needs_review' ? 'bg-blue-50 text-blue-700' : 'bg-slate-100 text-slate-500';
  return <span title={count === undefined ? labels[status] : `${labels[status]} ${count} 条规则`} className={`inline-flex shrink-0 items-center justify-center gap-1.5 rounded-full px-2.5 py-1.5 ${count === undefined ? 'text-[11px] font-medium' : 'text-xs font-semibold'} tabular-nums ${tone}`}>
    <Icon className={`size-3.5 ${status === 'running' ? 'animate-spin motion-reduce:animate-none' : ''}`} />
    {labels[status]}{count !== undefined ? ` ${count}` : ''}
  </span>;
}

function RuleBadges({ option, severity, summaryOptions, compact = false }: { option: RuleFilterOption; severity: RuleFilterLevel; summaryOptions?: RuleFilterOption[]; compact?: boolean }) {
  const visibleLevels = levels.filter(level => (severity === 'all' || severity === level) && option.counts[level] > 0);
  const options = summaryOptions || [option];
  const executionCount = options.reduce((total, rule) => total + warningCount(rule), 0);
  const showsExecutionWarning = (severity === 'all' || severity === 'execution') && executionCount > 0;
  const renderSeverityBadge = (level: RuleSeverity) => {
    const Icon = level === 'error' ? CircleX : level === 'warning' ? TriangleAlert : Info;
    const tone = level === 'error' ? 'bg-rose-50 text-rose-600' : level === 'warning' ? 'bg-amber-50 text-amber-600' : 'bg-blue-50 text-blue-600';
    return <span key={level} data-severity={level} title={`${levelLabels[level]} ${option.counts[level]} 处`} className={`${countBadgeClassName} ${tone}`}><Icon className="size-3.5" />{option.counts[level]}</span>;
  };
  return <span className="flex min-w-0 flex-wrap items-center justify-end gap-1.5">
    {visibleLevels.filter(level => level !== 'info').map(renderSeverityBadge)}
    {showsExecutionWarning ? <span data-severity="execution" title={compact ? `规则未实现警告 ${executionCount} 项` : '规则未实现警告'} className={`${compact ? countBadgeClassName : 'inline-flex min-w-10 shrink-0 items-center justify-center gap-1 rounded-full px-2.5 py-1.5 text-[11px] font-medium'} bg-violet-50 text-violet-700`}><ShieldAlert className="size-3.5" />{compact ? executionCount : '规则未实现警告'}</span> : null}
    {visibleLevels.includes('info') ? renderSeverityBadge('info') : null}
    {incompleteStatuses.map(status => {
      // Aggregate exactly the badges shown on rule rows, including deduplication.
      const count = options.filter(rule => hasStatusBadge(rule, status, severity)).length;
      return count ? <ExecutionStatus key={status} status={status} count={summaryOptions ? count : undefined} /> : null;
    })}
    {severity !== 'execution' && option.status === 'completed' && !visibleLevels.length && !executionCount ? <span className={`${countBadgeClassName} bg-emerald-50 text-emerald-600`}><CheckCircle2 className="size-3.5" />0</span> : null}
  </span>;
}

export function RuleFilter({ options, value, onValueChange, totalCount, severity = 'all' }: {
  options: RuleFilterOption[];
  value: string;
  onValueChange: (value: string) => void;
  totalCount: number;
  severity?: RuleFilterLevel;
}) {
  const visible = options.filter(option => isRuleVisible(option, severity))
    .sort((a, b) => resultOrder(a) - resultOrder(b));
  const counts = options.reduce((result, option) => ({ error: result.error + option.counts.error, warning: result.warning + option.counts.warning, info: result.info + option.counts.info }), { error: 0, warning: 0, info: 0 });
  const executionWarningCount = visible.reduce((total, option) => total + warningCount(option), 0);
  const overallStatus = visible.some(o => o.status === 'running') ? 'running' : visible.some(o => o.status === 'error') ? 'error' : executionWarningCount > 0 ? 'execution_warning' : visible.some(o => o.status === 'needs_review') ? 'needs_review' : visible.some(o => o.status === 'not_applicable') ? 'not_applicable' : 'completed';
  const all: RuleFilterOption = { id: 'all', title: '全部检查项', count: totalCount, counts, status: overallStatus,
    executionWarningCount };
  const selected = visible.find(option => option.id === value) || all;
  return <Select.Root value={selected.id} onValueChange={onValueChange}>
    <Select.Trigger aria-label="按检查项筛选" className="group mt-3 flex min-h-13 w-full items-center gap-2.5 rounded-2xl border border-slate-200 bg-white px-3 py-3 text-left text-sm text-slate-800 outline-none transition-colors hover:border-slate-300 focus-visible:border-brand-500 focus-visible:ring-2 focus-visible:ring-brand-100 data-[state=open]:border-slate-300 motion-reduce:transition-none">
      <Funnel className="size-4 shrink-0 text-slate-500" aria-hidden="true" />
      <span className="flex min-w-0 flex-1 items-center gap-1.5 font-medium"><span className="min-w-0 truncate" title={selected.title}><Select.Value>{selected.title}</Select.Value></span><ExperimentalBadge ruleId={selected.id} /></span>
      <span aria-hidden="true" className="max-w-[65%] min-w-0 shrink-0"><RuleBadges compact option={selected} severity={severity} summaryOptions={selected.id === 'all' ? visible : undefined} /></span>
      <Select.Icon asChild><ChevronDown className="size-4 shrink-0 text-slate-400 transition-transform group-data-[state=open]:rotate-180 motion-reduce:transition-none" /></Select.Icon>
    </Select.Trigger>
    <Select.Portal>
      <Select.Content position="popper" align="start" sideOffset={8} collisionPadding={12}
        className="z-50 flex max-h-[min(510px,var(--radix-select-content-available-height))] w-[var(--radix-select-trigger-width)] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white p-2 text-slate-800 shadow-lg shadow-slate-900/5">
        <Select.ScrollUpButton className="flex h-5 shrink-0 items-center justify-center text-slate-400"><ChevronUp className="size-3.5" /></Select.ScrollUpButton>
        <Select.Viewport>
          {[all, ...visible].map(option => <Select.Item key={option.id} value={option.id} textValue={option.title}
            className={`relative flex min-h-13 cursor-default select-none items-center gap-3 rounded-xl py-3 pr-3 pl-8 text-xs outline-none data-[highlighted]:bg-slate-50 data-[state=checked]:font-semibold ${option.id === 'all' ? 'mb-1 border-b border-slate-100 text-sm font-semibold' : ''}`}>
            <Select.ItemIndicator className="absolute left-2.5 text-brand-600"><Check className="size-3.5" /></Select.ItemIndicator>
            <span className="flex min-w-0 flex-1 items-center gap-1.5 leading-5"><Select.ItemText className="min-w-0 whitespace-normal">{option.title}<span className="sr-only">，{statusLabel(option, severity)}</span></Select.ItemText><ExperimentalBadge ruleId={option.id} /></span>
            <span aria-hidden="true" className="max-w-[55%] shrink-0">{option.id === 'all' ? <span className="whitespace-nowrap text-[11px] font-normal text-slate-400">{visible.length} 条规则</span> : <RuleBadges option={option} severity={severity} />}</span>
          </Select.Item>)}
        </Select.Viewport>
        <Select.ScrollDownButton className="flex h-5 shrink-0 items-center justify-center text-slate-400"><ChevronDown className="size-3.5" /></Select.ScrollDownButton>
      </Select.Content>
    </Select.Portal>
  </Select.Root>;
}
