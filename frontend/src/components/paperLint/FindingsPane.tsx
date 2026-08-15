import { Check, CheckCircle2, MapPin } from 'lucide-react';
import { useMemo, useState } from 'react';
import type { PaperLintRule } from '../../api/paperLint';
import { Button, StatusBadge } from '../ui';
import { findingPageLabel, type PaperLintFindingItem } from './model';

type Props = {
  findings: PaperLintFindingItem[];
  rules: PaperLintRule[];
  activeFindingKey: string | null;
  activeAnchorId: string | null;
  onFindingClick: (key: string) => void;
  onAnchorClick: (key: string, anchorId: string) => void;
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
}: Props) {
  const [filter, setFilter] = useState<'all' | 'error' | 'warning' | 'info'>('all');
  const [ruleFilter, setRuleFilter] = useState('all');
  const [handledKeys, setHandledKeys] = useState<string[]>([]);
  const ruleNames = useMemo(() => new Map(rules.map((rule) => [rule.rule_id, rule.title])), [rules]);
  const ruleIds = Array.from(new Set(findings.map((item) => item.ruleRun.rule_id)));
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
            <p className="mt-1 text-xs text-slate-500">规则未发现问题，或该规则不适用于此 PDF。</p>
          </div>
        ) : (
          filtered.map((item) => {
            const active = item.key === activeFindingKey;
            const page = findingPageLabel(item);
            const excerpt = item.finding.location?.text_excerpt || item.finding.anchors?.[0]?.location.text_excerpt;
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
                        <MapPin className="size-3" />第 {page} 页
                      </span>
                    ) : (
                      <span className="text-xs text-slate-400">暂无精确定位</span>
                    )}
                    <Button
                      size="sm"
                      variant={handledKeys.includes(item.key) ? 'secondary' : 'ghost'}
                      className="px-2"
                      aria-label={handledKeys.includes(item.key) ? '取消已处理标记' : '标记为已处理'}
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
                {active && item.finding.suggestion ? (
                  <div className="mt-3 rounded-lg bg-white p-3 text-xs leading-5 text-slate-600">
                    <strong className="text-slate-800">修改建议：</strong>
                    {item.finding.suggestion}
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
