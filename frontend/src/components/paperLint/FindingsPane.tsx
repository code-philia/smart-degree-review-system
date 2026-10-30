import { Bot, Check, CheckCircle2, MapPin, ThumbsDown, ThumbsUp } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import type { PaperLintRule } from '../../api/paperLint';
import type { RepairSuggestion } from '../../api/repairSuggestions';
import type { FindingFeedback, SuggestionFeedback } from '../../api/feedback';
import { Button, StatusBadge } from '../ui';
import { comparePaperLintRuleIds, findingPageLabel, type PaperLintFindingItem } from './model';

type Props = {
  findings: PaperLintFindingItem[];
  rules: PaperLintRule[];
  activeFindingKey: string | null;
  activeAnchorId: string | null;
  onFindingClick: (key: string) => void;
  onAnchorClick: (key: string, anchorId: string) => void;
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
  onFindingFeedbackReason?: (finding: PaperLintFindingItem, reasonCode: string | null, reasonText: string | null) => void;
  onFindingFeedbackCancel?: (finding: PaperLintFindingItem) => void;
  onSuggestionFeedback?: (finding: PaperLintFindingItem, value: 'positive' | 'negative') => void;
  onSuggestionFeedbackReason?: (finding: PaperLintFindingItem, reasonCode: string | null, reasonText: string | null) => void;
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
      <span className="mr-1 text-xs font-semibold text-rose-700">修改前：</span>
      <span className="rounded bg-rose-100 px-1 text-rose-800 line-through" title="检测到的原文片段">{parts.before}</span>
      <span className="mx-1 text-slate-500">改为</span>
      <span className="mr-1 text-xs font-semibold text-emerald-700">修改后：</span>
      <span className="rounded bg-emerald-100 px-1 text-emerald-800" title="建议修改后的文字">{parts.after}</span>
      {parts.suffix}
    </p>
  );
}


function FeedbackControls({
  label, feedback, reasons, onValue, onReason, onCancel,
}: {
  label: string;
  feedback?: FindingFeedback | SuggestionFeedback | null;
  reasons: [string, string][];
  onValue: (value: 'positive' | 'negative') => void;
  onReason: (code: string | null, text: string | null) => void;
  onCancel: () => void;
}) {
  const [reasonCode, setReasonCode] = useState(feedback?.reason_code || '');
  const [reasonText, setReasonText] = useState(feedback?.reason_text || '');
  useEffect(() => {
    setReasonCode(feedback?.reason_code || '');
    setReasonText(feedback?.reason_text || '');
  }, [feedback?.id, feedback?.reason_code, feedback?.reason_text]);
  return (
    <div className="mt-3 rounded-lg border border-slate-100 bg-slate-50 p-2" onClick={(event) => event.stopPropagation()}>
      <div className="flex items-center gap-2">
        <span className="text-xs text-slate-500">{label}</span>
        <Button size="sm" variant="ghost" className={feedback?.feedback_value === 'positive' ? 'bg-emerald-100 text-emerald-700 ring-1 ring-emerald-300 hover:bg-emerald-200' : ''} aria-label="有帮助" aria-pressed={feedback?.feedback_value === 'positive'} onClick={() => onValue('positive')}><ThumbsUp className="size-3.5" /></Button>
        <Button size="sm" variant="ghost" className={feedback?.feedback_value === 'negative' ? 'bg-red-100 text-red-700 ring-1 ring-red-300 hover:bg-red-200' : ''} aria-label="需要改进" aria-pressed={feedback?.feedback_value === 'negative'} onClick={() => onValue('negative')}><ThumbsDown className="size-3.5" /></Button>
        {feedback ? <Button size="sm" variant="ghost" className="ml-auto text-xs" onClick={onCancel}>取消评价</Button> : null}
      </div>
      {feedback?.feedback_value === 'negative' ? <div className="mt-2 space-y-2">
        <select aria-label="负面反馈原因" className="w-full rounded-md border border-slate-200 bg-white px-2 py-1 text-xs" value={reasonCode} onChange={(event) => setReasonCode(event.target.value)}>
          <option value="">可选：选择原因</option>
          {reasons.map(([value, text]) => <option key={value} value={value}>{text}</option>)}
        </select>
        <textarea aria-label="反馈补充说明" className="min-h-12 w-full rounded-md border border-slate-200 bg-white px-2 py-1 text-xs" placeholder="可选补充说明" value={reasonText} onChange={(event) => setReasonText(event.target.value)} />
        <Button size="sm" variant="ghost" onClick={() => onReason(reasonCode || null, reasonText || null)}>保存原因</Button>
      </div> : null}
    </div>
  );
}

export function FindingsPane({
  findings,
  rules,
  activeFindingKey,
  activeAnchorId,
  onFindingClick,
  onAnchorClick,
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
  const [filter, setFilter] = useState<'all' | 'error' | 'warning' | 'info'>('all');
  const [ruleFilter, setRuleFilter] = useState('all');
  const [handledKeys, setHandledKeys] = useState<string[]>([]);
  const ruleNames = useMemo(() => new Map(rules.map((rule) => [rule.rule_id, rule.title])), [rules]);
  const ruleIds = Array.from(new Set(findings.map((item) => item.ruleRun.rule_id))).sort(comparePaperLintRuleIds);
  const filtered = findings.filter(
    (item) =>
      (filter === 'all' || item.ruleRun.severity === filter) &&
      (ruleFilter === 'all' || item.ruleRun.rule_id === ruleFilter),
  );

  return (
    <section className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white">
      <div className="border-b border-slate-200 p-3">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-sm font-bold text-slate-900">审查问题</h2>
          <StatusBadge>{filtered.length} 项</StatusBadge>
        </div>
        <div className="mt-2 flex flex-wrap gap-1">
          {(['all', 'error', 'warning', 'info'] as const).map((value) => (
            <Button
              key={value}
              size="sm"
              variant={filter === value ? 'secondary' : 'ghost'}
              aria-pressed={filter === value}
              onClick={() => setFilter(value)}
            >
              {value === 'all' ? '全部' : severityLabels[value]}
            </Button>
          ))}
        </div>
        {ruleIds.length > 1 ? (
          <select
            aria-label="按检查项筛选"
            className="mt-2 w-full rounded-md border border-slate-200 bg-white px-2 py-1.5 text-xs text-slate-700"
            value={ruleFilter}
            onChange={(event) => setRuleFilter(event.target.value)}
          >
            <option value="all">全部检查项</option>
            {ruleIds.map((ruleId) => (
              <option key={ruleId} value={ruleId}>
                {ruleNames.get(ruleId) || ruleId}
              </option>
            ))}
          </select>
        ) : null}
      </div>
      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-3">
        {filtered.length === 0 ? (
          <div className="flex h-full min-h-60 flex-col items-center justify-center text-center">
            <CheckCircle2 className="size-8 text-success-600" />
            <p className="mt-3 text-sm font-bold text-slate-900">当前筛选下没有问题</p>
            <p className="mt-1 text-xs text-slate-500">请结合各规则执行状态查看；证据不足的内容仍可能无法判定。</p>
          </div>
        ) : (
          filtered.map((item) => {
            const active = item.key === activeFindingKey;
            const page = findingPageLabel(item);
            const repair = repairSuggestionByFindingKey[item.key];
            const repairError = repairSuggestionErrorByFindingKey[item.key];
            const generating = repairSuggestionLoadingByFindingKey[item.key] || repairSuggestionLoadingKey === item.key;
            const repairEnabled = supportsRepairSuggestion(item);
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
                      <span className="inline-flex shrink-0 items-center gap-1 text-xs text-slate-500">
                        <MapPin className="size-3" />
                        PDF 第 {page} 页
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
                  onReason={(code, text) => onFindingFeedbackReason?.(item, code, text)}
                  onCancel={() => onFindingFeedbackCancel?.(item)}
                /> : null}
                {page ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="mt-2"
                    aria-label={`跳到 PDF 第 ${page} 页`}
                    onClick={(event) => {
                      event.stopPropagation();
                      onFindingClick(item.key);
                    }}
                  >
                    跳到 PDF 第 {page} 页
                  </Button>
                ) : null}
                {active && item.finding.source_kind === 'synthetic' ? <p className="mt-2 text-xs text-slate-600">该处来自变异内容，未标记为原始 PDF 中的文本。</p> : null}
                {active && item.finding.suggestion && (!repairEnabled || (!onLoadRepairSuggestion && !onGenerateRepairSuggestion)) ? (
                  <div className="mt-3 rounded-lg bg-white p-3 text-xs leading-5 text-slate-600">
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
                        onReason={(code, text) => onSuggestionFeedbackReason?.(item, code, text)}
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
