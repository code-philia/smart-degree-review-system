import { Bot, Check, CheckCircle2, CircleAlert, CircleHelp, ListFilter, LoaderCircle, MapPin } from 'lucide-react';
import { useMemo, useState } from 'react';
import type { PaperLintRule, PaperLintRuleRun } from '../../api/paperLint';
import type { RepairSuggestion } from '../../api/repairSuggestions';
import type { FindingFeedback, SuggestionFeedback } from '../../api/feedback';
import { Button, StatusBadge } from '../ui';
import { comparePaperLintRuleIds, findingPageLabel, type PaperLintFindingItem } from './model';
import { FeedbackControls } from './FeedbackControls';
import { displayFindingPages, type PdfPageLabels } from './pageLabels';
import type { RuleExecutionWarning } from './model';
import { RuleFilter, type RuleFilterOption, type RuleSeverityCounts } from './RuleFilter';

type Props = {
  executionWarnings?: RuleExecutionWarning[];
  findings: PaperLintFindingItem[];
  running?: boolean;
  rules: PaperLintRule[];
  selectedRuleIds?: string[];
  ruleRuns?: PaperLintRuleRun[];
  activeFindingKey: string | null;
  activeAnchorId: string | null;
  onFindingClick: (key: string) => void;
  onAnchorClick: (key: string, anchorId: string) => void;
  pageLabels?: PdfPageLabels;
  repairSuggestionByFindingKey?: Record<string, RepairSuggestion | undefined>;
  repairSuggestionLoadingKey?: string | null;
  repairSuggestionLoadingByFindingKey?: Record<string, boolean>;
  repairSuggestionErrorByFindingKey?: Record<string, string | undefined>;
  onLoadRepairSuggestion?: (finding: PaperLintFindingItem) => void;
  onGenerateRepairSuggestion?: (finding: PaperLintFindingItem) => void;
  supportsRepairSuggestion?: (finding: PaperLintFindingItem) => boolean;
  forceNewRepairSuggestion?: boolean;
  findingFeedbackByKey?: Record<string, FindingFeedback | null | undefined>;
  suggestionFeedbackByFindingKey?: Record<string, SuggestionFeedback | null | undefined>;
  onFindingFeedback?: (finding: PaperLintFindingItem, value: 'positive' | 'negative') => void;
  onFindingFeedbackReason?: (finding: PaperLintFindingItem, reasonCode: string | null, reasonText: string | null) => void | Promise<void>;
  onFindingFeedbackCancel?: (finding: PaperLintFindingItem) => void;
  onSuggestionFeedback?: (finding: PaperLintFindingItem, value: 'positive' | 'negative') => void;
  onSuggestionFeedbackReason?: (finding: PaperLintFindingItem, reasonCode: string | null, reasonText: string | null) => void | Promise<void>;
  onSuggestionFeedbackCancel?: (finding: PaperLintFindingItem) => void;
};

const tones = { error: 'danger', warning: 'warning', info: 'info' } as const;
const severityLabels = { error: '严重', warning: '警告', info: '提示' };

function repairActionParts(instruction: string) {
  const text = instruction.trim();
  const match = text.match(/^(.*?)(?:将|把)\s*[“"「『]([^”"」』]+)[”"」』]\s*(?:修改为|改为|替换为)\s*[“"「『]([^”"」』]+)[”"」』](.*)$/s);
  if (match) return { prefix: `${match[1]}${match[1] ? ' ' : ''}`, before: match[2], after: match[3], suffix: match[4] };
  // Also accept the explicit format emitted by some repair-model responses.
  const labelled = text.match(/^(.*?)(?:修改前|原文)\s*[:：]\s*([\s\S]*?)\s*(?:修改后|建议修改后|改为)\s*[:：]\s*([\s\S]*)$/);
  if (labelled) return { prefix: labelled[1], before: labelled[2].trim(), after: labelled[3].trim(), suffix: '' };
  // Keep the complete model instruction; do not hide its context behind a UI truncation.
  return { text };
}

function RepairAction({ instruction }: { instruction: string }) {
  const parts = repairActionParts(instruction);
  if (!('before' in parts)) return <p>{parts.text}</p>;
  return (
    <p className="whitespace-pre-wrap break-words">
      {parts.prefix}
      <span className="mr-1 text-xs font-semibold text-emerald-700">建议修改为：</span>
      <span className="rounded bg-emerald-100 px-1 text-emerald-800" title="建议修改后的文字">{parts.after}</span>
      {parts.suffix}
    </p>
  );
}


export function FindingsPane({
  executionWarnings = [],
  findings,
  running = false,
  rules,
  selectedRuleIds,
  ruleRuns,
  activeFindingKey,
  activeAnchorId,
  onFindingClick,
  onAnchorClick,
  pageLabels = {},
  repairSuggestionByFindingKey = {},
  repairSuggestionLoadingKey = null,
  repairSuggestionLoadingByFindingKey = {},
  repairSuggestionErrorByFindingKey = {},
  onLoadRepairSuggestion,
  onGenerateRepairSuggestion,
  supportsRepairSuggestion = () => true,
  findingFeedbackByKey = {},
  suggestionFeedbackByFindingKey = {},
  onFindingFeedback,
  onFindingFeedbackReason,
  onFindingFeedbackCancel,
  onSuggestionFeedback,
  onSuggestionFeedbackReason,
  onSuggestionFeedbackCancel,
}: Props) {
  const [filter, setFilter] = useState<'all' | 'error' | 'warning' | 'info' | 'execution'>('all');
  const [ruleFilter, setRuleFilter] = useState('all');
  const [handledKeys, setHandledKeys] = useState<string[]>([]);
  const ruleNames = useMemo(() => new Map(rules.map((rule) => [rule.rule_id, rule.title])), [rules]);
  const ruleIds = Array.from(new Set(selectedRuleIds ?? [...rules.map(rule => rule.rule_id), ...findings.map(item => item.ruleRun.rule_id)])).sort(comparePaperLintRuleIds);
  const runById = new Map([...findings.map(item => item.ruleRun), ...(ruleRuns || [])].map(run => [run.rule_id, run]));
  const counts = new Map<string, RuleSeverityCounts>();
  const severityTotals: RuleSeverityCounts = { error: 0, warning: 0, info: 0 };
  findings.forEach(item => {
    const entry = counts.get(item.ruleRun.rule_id) || { error: 0, warning: 0, info: 0 };
    entry[item.ruleRun.severity]++;
    severityTotals[item.ruleRun.severity]++;
    counts.set(item.ruleRun.rule_id, entry);
  });
  const ruleOptions: RuleFilterOption[] = ruleIds.map(id => {
    const run = runById.get(id);
    const status = !run ? (running ? 'running' : ruleRuns ? 'needs_review' : 'completed')
      : run.execution_status === 'error' ? 'error'
      : run.execution_status === 'unsupported' || run.outcome === 'inconclusive' ? 'needs_review'
      : run.outcome === 'not_applicable' ? 'not_applicable' : 'completed';
    const ruleCounts = counts.get(id) || { error: 0, warning: 0, info: 0 };
    return { id, title: ruleNames.get(id) || id, count: ruleCounts.error + ruleCounts.warning + ruleCounts.info, counts: ruleCounts, status };
  });
  // A completed rule outside the chosen level must not remain as a hidden selection.
  const chosenOption = ruleOptions.find(option => option.id === ruleFilter);
  const effectiveRuleFilter = chosenOption && filter !== 'all' && filter !== 'execution' && !chosenOption.counts[filter]
    && !['running', 'error', 'needs_review'].includes(chosenOption.status) ? 'all' : ruleFilter;
  const selectedOption = ruleOptions.find(option => option.id === effectiveRuleFilter);
  const selectedRun = runById.get(effectiveRuleFilter);
  const selectedTotal = selectedOption?.count ?? findings.length;
  const pending = selectedOption ? selectedOption.status === 'running' : running && ruleOptions.some(option => option.status === 'running');
  const incomplete = selectedOption ? ['error', 'needs_review', 'not_applicable'].includes(selectedOption.status)
    : executionWarnings.length > 0 || ruleOptions.some(option => option.status !== 'completed');
  const severityEmpty = !pending && selectedTotal > 0 && filter !== 'all' && filter !== 'execution';
  const emptyTitle = pending ? '正在检测相关问题'
    : severityEmpty ? `当前筛选未发现${severityLabels[filter as keyof typeof severityLabels]}级别的问题`
    : selectedOption?.status === 'error' ? '本规则检测失败'
    : selectedOption?.status === 'needs_review' ? '本规则暂无法判定'
    : selectedOption?.status === 'not_applicable' ? '本规则不适用'
    : incomplete ? '部分规则未完成有效检测'
    : selectedOption ? '本规则未检测出问题' : '未检测出问题';
  const emptyDescription = pending ? '检测完成后自动更新，您可以先查看其他已完成规则的结果。'
    : severityEmpty ? `${selectedOption ? '该规则' : '当前报告'}共发现 ${selectedTotal} 处问题，分布在其他级别。`
    : incomplete ? selectedRun?.message || '请在规则下拉框查看检测状态；证据不足或检测失败不代表没有问题。'
    : '基于当前规范性检测规则，证据不足的内容仍可能无法判定，检测结果仅供参考';
  const EmptyIcon = pending ? LoaderCircle : severityEmpty ? ListFilter : selectedOption?.status === 'error' ? CircleAlert : incomplete ? CircleHelp : CheckCircle2;
  const filtered = findings.filter(
    (item) =>
      (filter === 'all' || item.ruleRun.severity === filter) &&
      (effectiveRuleFilter === 'all' || item.ruleRun.rule_id === effectiveRuleFilter),
  );

  return (
    <section className="@container/report flex min-h-0 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white">
      <div className="border-b border-slate-200 p-4">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-sm font-bold text-slate-900">检测结果</h2>
          <span className="text-sm font-medium text-slate-700 tabular-nums">{findings.length} 项问题</span>
        </div>
        <div className="mt-2 flex flex-wrap gap-1">
          {(['all', 'error', 'warning', 'info'] as const).map((value) => (
            <button
              key={value}
              type="button"
              className={`inline-flex min-h-8 items-center gap-1 rounded-full border px-3 py-1.5 text-xs transition-colors ${filter === value ? 'border-slate-300 bg-white font-semibold text-slate-900 shadow-xs' : 'border-transparent text-slate-500 hover:bg-slate-50'}`}
              aria-pressed={filter === value}
              onClick={() => {
                setFilter(value);
                if (value !== 'all' && chosenOption && !chosenOption.counts[value] && !['running', 'error', 'needs_review'].includes(chosenOption.status)) setRuleFilter('all');
              }}
            >
              {value === 'all' ? '全部' : <>{severityLabels[value]} <span className="tabular-nums">{severityTotals[value]}</span></>}
            </button>
          ))}
          {executionWarnings.length ? <Button size="sm" variant={filter === 'execution' ? 'secondary' : 'ghost'} aria-pressed={filter === 'execution'} onClick={() => setFilter('execution')}>规则未实现警告（{executionWarnings.length}）</Button> : null}
        </div>
        {ruleIds.length > 0 ? (
          <RuleFilter options={ruleOptions} value={effectiveRuleFilter} onValueChange={setRuleFilter} totalCount={findings.length} severity={filter === 'execution' ? 'all' : filter} />
        ) : null}
      </div>
      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-3">
        {filter === 'execution' ? <>
          <p className="rounded-lg bg-slate-50 p-3 text-sm leading-6 text-slate-600">如需使用以下规则，请按建议内容调整；如无需使用，请忽略以下内容</p>
          {executionWarnings.map((warning, index) => (
            <article key={index} className="rounded-lg border border-rose-200 p-3">
              <h3 className="text-sm font-bold text-rose-700">{warning.title}</h3>
              {warning.preconditionId ? (
                <>
                  <p className="mt-2 text-sm leading-6 text-slate-700">
                    <strong>检测说明：</strong>本规则目前仅支持核验摘要中与<strong>实验数据</strong>相关的论点论据
                  </p>
                  <h4 className="mt-4 text-base font-bold leading-7 text-slate-900">
                    {warning.preconditionId === 'abstract_numeric'
                      ? <>摘要中不存在可核验的<strong>含有数值的</strong>论点</>
                      : warning.issueTitle}
                  </h4>
                  <div className="mt-3 rounded-lg bg-slate-50 p-3 text-sm leading-6 text-slate-700">
                    <p><strong>符合要求的示例：</strong></p>
                    <p className="mt-1 whitespace-pre-line">{warning.example}</p>
                    <p className="mt-3"><strong>说明：</strong>{warning.explanation}</p>
                  </div>
                  <p className="mt-3 rounded-lg bg-slate-50 p-3 text-sm leading-6 text-slate-700">
                    <strong>调整建议：</strong>{warning.suggestion}
                  </p>
                  {warning.note ? <p className="mt-3 text-sm leading-6 text-slate-600">{warning.note}</p> : null}
                </>
              ) : (
                <>
                  <p className="mt-2 text-sm leading-6 text-slate-700">{warning.reason}</p>
                  <p className="mt-3 rounded-lg bg-slate-50 p-3 text-sm leading-6"><strong>调整建议：</strong>{warning.suggestion}</p>
                </>
              )}
            </article>
          ))}
        </> : filtered.length === 0 ? (
          <div className="flex h-full min-h-60 flex-col items-center justify-center text-center">
            <EmptyIcon data-testid={!pending && !incomplete && !severityEmpty ? 'rule-empty-icon' : undefined} className={`size-8 ${pending ? 'animate-spin text-brand-600 motion-reduce:animate-none' : severityEmpty ? 'text-slate-400' : incomplete ? 'text-amber-600' : 'text-success-600'}`} />
            <p className="mt-3 text-sm font-bold text-slate-900">{emptyTitle}</p>
            <p className="mt-1 max-w-sm text-xs leading-6 text-slate-500">{emptyDescription}</p>
            {severityEmpty ? <Button className="mt-3" size="sm" variant="secondary" onClick={() => setFilter('all')}>查看全部级别</Button> : null}
          </div>
        ) : (
          filtered.map((item) => {
            const active = item.key === activeFindingKey;
            const page = displayFindingPages(item, pageLabels);
            const physicalPages = findingPageLabel(item);
            const repair = repairSuggestionByFindingKey[item.key];
            const repairError = repairSuggestionErrorByFindingKey[item.key];
            const generating = repairSuggestionLoadingByFindingKey[item.key] || repairSuggestionLoadingKey === item.key;
            const numeric = item.ruleRun.rule_id === 'abstract_numeric_consistency_check';
            const repairEnabled = !numeric && supportsRepairSuggestion(item);
            const findingFeedback = findingFeedbackByKey[item.key];
            const suggestionFeedback = suggestionFeedbackByFindingKey[item.key];
            const showRepairSuggestion = Boolean(onGenerateRepairSuggestion || repair || generating || repairError);
            return (
              <article
                key={item.key}
                data-finding-key={item.key}
                className={`cursor-pointer rounded-lg border border-l-4 p-3 transition ${
                  active ? 'border-brand-500 bg-brand-50 ring-1 ring-brand-100' : 'border-slate-200 hover:bg-slate-50'
                }`}
                role="button"
                tabIndex={0}
                aria-current={active || undefined}
                onClick={() => onFindingClick(item.key)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    onFindingClick(item.key);
                  }
                }}
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <StatusBadge tone={tones[item.ruleRun.severity]}>
                      {severityLabels[item.ruleRun.severity]}
                    </StatusBadge>
                    <h3 className="mt-2 text-sm font-bold text-slate-900">
                      {ruleNames.get(item.ruleRun.rule_id) || item.ruleRun.rule_id}
                    </h3>
                  </div>
                  <div className="flex items-center gap-1">
                    {page ? (
                      <span className="inline-flex shrink-0 items-center gap-1 text-xs text-slate-500" title={`PDF 第 ${physicalPages} 页`}>
                        <MapPin className="size-3" />
                        {page}
                      </span>
                    ) : (
                      <span className="text-xs text-slate-400">暂无精确定位</span>
                    )}
                    <Button
                      size="sm"
                      variant={handledKeys.includes(item.key) ? 'secondary' : 'ghost'}
                      className="px-2"
                      aria-label={handledKeys.includes(item.key) ? '取消已处理标记' : '标记为已处理'}
                      title="本次页面的临时标记，刷新后不保留"
                      onClick={(event) => {
                        event.stopPropagation();
                        setHandledKeys((current) =>
                          current.includes(item.key)
                            ? current.filter((key) => key !== item.key)
                            : [...current, item.key],
                        );
                      }}
                    >
                      <Check className="size-3.5" />
                    </Button>
                  </div>
                </div>
                <p className="mt-2 text-sm leading-6 text-slate-700">{item.finding.message}</p>
                {onFindingFeedback ? <FeedbackControls
                  label="这个问题的判断是否准确？"
                  feedback={findingFeedback}
                  reasons={[['false_positive', '误报'], ['location_inaccurate', '定位不准'], ['description_unclear', '说明不清'], ['other', '其他']]}
                  onValue={(value) => onFindingFeedback(item, value)}
                  onReason={onFindingFeedbackReason ? (code, text) => onFindingFeedbackReason(item, code, text) : undefined}
                  onCancel={() => onFindingFeedbackCancel?.(item)}
                /> : null}
                {page ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="mt-2"
                    aria-label={`跳到${page.startsWith('PDF ') ? ' ' : ''}${page}`}
                    onClick={(event) => {
                      event.stopPropagation();
                      onFindingClick(item.key);
                    }}
                  >
                    跳到{page.startsWith('PDF ') ? ' ' : ''}{page}
                  </Button>
                ) : null}
                {active && item.finding.source_kind === 'synthetic' ? <p className="mt-2 text-xs text-slate-600">该处来自变异内容，未标记为原始 PDF 中的文本。</p> : null}
                {(numeric || active) && item.finding.suggestion && (!repairEnabled || (!onLoadRepairSuggestion && !onGenerateRepairSuggestion)) ? (
                  <div className={`mt-3 rounded-lg bg-white p-3 text-slate-600 ${numeric ? 'text-sm leading-6' : 'text-xs leading-5'}`}>
                    <strong className="text-slate-800">修改建议：</strong>
                    {item.finding.suggestion}
                  </div>
                ) : null}
                {repairEnabled && (onLoadRepairSuggestion || onGenerateRepairSuggestion) && showRepairSuggestion ? (
                  <div className="mt-3 border-t border-slate-100 pt-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="text-xs font-bold text-slate-800">修复建议</p>
                      {onGenerateRepairSuggestion ? (
                      <Button
                        size="sm"
                        variant="secondary"
                        disabled={generating || !onGenerateRepairSuggestion}
                        onClick={(event) => {
                          event.stopPropagation();
                          onGenerateRepairSuggestion?.(item);
                        }}
                      >
                        <Bot className="size-3.5" />
                        {generating ? '正在生成建议…' : repair ? '重新生成修复建议' : '获取修复建议'}
                      </Button>
                      ) : null}
                    </div>
                    {!repair && !repairError ? <p className="mt-2 text-xs text-slate-500">{generating ? '正在生成建议…' : '尚未生成建议。'}</p> : null}
                    {repairError ? (
                      <div className="mt-2 text-xs leading-5 text-slate-600" role="status">
                        <p>{repair ? '本次更新暂未完成，继续显示已保存的修复建议。' : (repairError || '修复建议暂未生成，可点击按钮重试。')}</p>
                        {!repair && item.finding.suggestion ? (
                          <p className="mt-2 rounded-lg bg-slate-50 p-3"><strong>规则修改提示：</strong>{item.finding.suggestion}</p>
                        ) : null}
                      </div>
                    ) : null}
                    {repair ? (
                      <>
                      <div className="mt-3 space-y-3 rounded-lg bg-sky-50 p-3 text-xs leading-5 text-slate-700">
                        <div>
                          <div className="space-y-2">
                            {repair.actions.map((action, index) => (
                              <RepairAction key={`${action.instruction}-${index}`} instruction={action.instruction} />
                            ))}
                          </div>
                        </div>
                        <p className="text-[11px] text-slate-500">
                          {repair.status === 'suggested'
                            ? '可执行建议'
                            : repair.status === 'evidence_conflict'
                              ? '证据与告警存在冲突：暂不应仅依据该告警修改论文，请人工复核规则结果。'
                              : repair.missing_context?.length
                                ? '需要核对相关原文上下文后再决定修改方向'
                                : '需要补充明确的原文片段和定位后再确定修改。'}
                        </p>
                      </div>
                      {onSuggestionFeedback && repair.suggestion_id ? <FeedbackControls
                        label="这条修复建议是否有帮助？"
                        feedback={suggestionFeedback}
                        reasons={[['incorrect', '内容不正确'], ['not_directly_executable', '无法直接执行'], ['insufficient_basis', '依据不足'], ['unclear', '表达不清'], ['other', '其他']]}
                        onValue={(value) => onSuggestionFeedback(item, value)}
                        onReason={onSuggestionFeedbackReason ? (code, text) => onSuggestionFeedbackReason(item, code, text) : undefined}
                        onCancel={() => onSuggestionFeedbackCancel?.(item)}
                      /> : null}
                      </>
                    ) : null}
                  </div>
                ) : null}
                {handledKeys.includes(item.key) ? (
                  <p className="mt-2 text-xs font-semibold text-success-600">已标记为本次已处理</p>
                ) : null}
                {active && item.finding.anchors?.length ? (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {item.finding.anchors.map((anchor, index) => (
                      <Button
                        key={anchor.anchor_id}
                        size="sm"
                        variant={activeAnchorId === anchor.anchor_id ? 'secondary' : 'ghost'}
                        aria-pressed={activeAnchorId === anchor.anchor_id}
                        onClick={(event) => {
                          event.stopPropagation();
                          onAnchorClick(item.key, anchor.anchor_id);
                        }}
                      >
                        {anchor.label || `证据 ${index + 1}`}
                      </Button>
                    ))}
                  </div>
                ) : null}
              </article>
            );
          })
        )}
      </div>
    </section>
  );
}
