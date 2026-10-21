import { Bot, Check, CheckCircle2, MapPin } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import type { PaperLintRule } from '../../api/paperLint';
import { EvidenceLinks } from './CompilerEvidence';
import type { RepairSuggestion } from '../../api/repairSuggestions';
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
};

const tones = { error: 'danger', warning: 'warning', info: 'info' } as const;
const severityLabels = { error: '严重', warning: '警告', info: '提示' };

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

  useEffect(() => {
    if (onLoadRepairSuggestion) findings.filter(supportsRepairSuggestion).forEach(item => onLoadRepairSuggestion(item));
  }, [findings, onLoadRepairSuggestion, supportsRepairSuggestion]);

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
            const excerpt = item.finding.location?.text_excerpt || item.finding.anchors?.[0]?.location.text_excerpt;
            const evidence = (item.finding.evidence || []).filter((entry) => entry.kind !== 'normative_span' && !(entry.kind === 'source_span' && entry.quote === excerpt));
            const repair = repairSuggestionByFindingKey[item.key];
            const repairError = repairSuggestionErrorByFindingKey[item.key];
            const generating = repairSuggestionLoadingByFindingKey[item.key] || repairSuggestionLoadingKey === item.key;
            const repairEnabled = supportsRepairSuggestion(item);
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
                {active && evidence.length ? <EvidenceLinks items={evidence} /> : null}
                {active && item.finding.suggestion && (!repairEnabled || (!onLoadRepairSuggestion && !onGenerateRepairSuggestion)) ? (
                  <div className="mt-3 rounded-lg bg-white p-3 text-xs leading-5 text-slate-600">
                    <strong className="text-slate-800">修改建议：</strong>
                    {item.finding.suggestion}
                  </div>
                ) : null}
                {repairEnabled && (onLoadRepairSuggestion || onGenerateRepairSuggestion) && showRepairSuggestion ? (
                  <div className="mt-3 border-t border-slate-100 pt-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="text-xs font-bold text-slate-800">AI 修复建议</p>
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
                        {generating ? '正在准备建议…' : '重新生成修复建议'}
                      </Button>
                      ) : null}
                    </div>
                    {!repair && !repairError ? <p className="mt-2 text-xs text-slate-500">{generating ? (onGenerateRepairSuggestion ? '正在自动准备修复建议…' : '正在加载已保存建议…') : '修复建议将自动加载。'}</p> : null}
                    {repairError ? <p className="mt-2 text-xs text-danger-600">{onGenerateRepairSuggestion ? '生成失败' : '建议加载失败'}：{repairError}</p> : null}
                    {repair ? (
                      <div className="mt-3 space-y-3 rounded-lg bg-sky-50 p-3 text-xs leading-5 text-slate-700">
                        <div>
                          <div className="space-y-2">
                            {repair.actions.map((action, index) => (
                              <p key={`${action.instruction}-${index}`}>{action.instruction}</p>
                            ))}
                          </div>
                        </div>
                        <p className="text-[11px] text-slate-500">
                          {repair.status === 'suggested'
                            ? '可执行建议'
                            : repair.status === 'evidence_conflict'
                              ? '证据与告警存在冲突：暂不应仅依据该告警修改论文，请人工复核规则结果。'
                              : '需要补充上下文：请按上述建议核对相关内容。'}
                          {' · '}
                          {repair.provenance.model} · {repair.provenance.prompt_version}
                        </p>
                      </div>
                    ) : null}
                  </div>
                ) : null}
                {active && excerpt ? (
                  <p className="mt-2 rounded-lg bg-slate-100 px-3 py-2 text-xs leading-5 text-slate-600">
                    原文：{excerpt}
                  </p>
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
