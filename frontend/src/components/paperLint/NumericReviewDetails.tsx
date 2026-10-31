import { useState } from 'react';
import type { PaperLintRuleRun } from '../../api/paperLint';
import type { PaperLintFindingItem } from './model';

const conditionOrder = ['abstract_numeric', 'contribution_mapping', 'experiment_subsection'];
const labels: Record<string, string> = {
  abstract_numeric: '摘要中存在可核验的数值型论点',
  contribution_mapping: '数值型论点已映射到研究贡献',
  experiment_subsection: '数值型论点已映射到实验子章节',
};
const fixedSuggestions: Record<string, string> = {
  abstract_numeric: '请在摘要中补充可与正文实验结果对应的明确数值、指标和条件；如果摘要本身没有数值型论点，则无需进行这项一致性核验。',
  contribution_mapping: '请将每个数值型研究结论明确关联到摘要中的具体方法或研究贡献，避免只给出孤立的数字。',
  experiment_subsection: '请在对应研究章节下组织实验设置、评估或结果小节，并确保数值型论点能够映射到真实实验依据。',
};
type Row = Record<string, unknown>;
type Filter = 'attention' | 'all' | 'inconsistent' | 'inconclusive' | 'consistent';
function objects(value: unknown): Row[] { return Array.isArray(value) ? value.filter((r): r is Row => Boolean(r && typeof r === 'object')) : []; }
function statusOf(row: Row) { return row.status === 'consistent' || row.status === 'inconsistent' ? row.status : 'inconclusive'; }
function pageNumber(value: unknown) { const page = Number(value); return Number.isInteger(page) && page > 0 ? page : null; }
function statusLabel(status: string) { return status === 'consistent' ? '一致' : status === 'inconsistent' ? '不一致' : '无法确定'; }
function statusTone(status: string) { return status === 'consistent' ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : status === 'inconsistent' ? 'border-rose-200 bg-rose-50 text-rose-700' : 'border-amber-200 bg-amber-50 text-amber-700'; }

type Props = {
  run: PaperLintRuleRun;
  findings?: PaperLintFindingItem[];
  onAnchorClick?: (findingKey: string, anchorId: string) => void;
  onPageClick?: (page: number) => void;
};

export function NumericReviewDetails({ run, findings = [], onAnchorClick, onPageClick }: Props) {
  const [filter, setFilter] = useState<Filter>('attention');
  if (run.rule_id !== 'abstract_numeric_consistency_check') return null;
  const params = run.params || {};
  const conditions = objects(params.preconditions);
  const results = objects(params.numeric_results);
  const mappings = objects(params.mappings);
  const contributions = objects(params.contributions);
  const trace = params.trace as Row | undefined;
  const counts = {
    consistent: results.filter(row => statusOf(row) === 'consistent').length,
    inconsistent: results.filter(row => statusOf(row) === 'inconsistent').length,
    inconclusive: results.filter(row => statusOf(row) === 'inconclusive').length,
  };
  const prerequisitesPassed = conditions.length > 0 && conditions.every(row => row.passed === true);
  const visibleResults = results.filter(row => filter === 'all' || statusOf(row) === filter || (filter === 'attention' && statusOf(row) !== 'consistent'));

  function EvidenceButton({ label, page, findingKey, anchorId }: { label: string; page: number | null; findingKey?: string; anchorId?: string }) {
    const canHighlight = Boolean(findingKey && anchorId && onAnchorClick);
    if (!page && !canHighlight) return null;
    return <button type="button" className="mt-2 inline-flex w-full items-center justify-between rounded-lg border border-brand-200 bg-brand-50 px-3 py-2 text-left text-xs font-semibold text-brand-700 hover:bg-brand-100" onClick={() => canHighlight ? onAnchorClick?.(findingKey!, anchorId!) : page ? onPageClick?.(page) : undefined}>
      <span>{label}</span><span>{page ? `第 ${page} 页 · 查看原文` : '查看原文'}</span>
    </button>;
  }

  return <div className="mt-4 space-y-5 text-sm" data-testid="numeric-review-details">
    <section aria-label="数值核验概览">
      <div className="flex flex-wrap items-end justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-[0.14em] text-brand-600">报告概览</p><h3 className="mt-1 text-lg font-bold text-slate-950">摘要数值型论点核验</h3></div><p className="text-xs text-slate-500">共核验 {results.length} 项论点</p></div>
      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">{([['总数', results.length, 'text-slate-900'], ['一致', counts.consistent, 'text-emerald-700'], ['不一致', counts.inconsistent, 'text-rose-700'], ['无法确定', counts.inconclusive, 'text-amber-700']] as const).map(([label, value, color]) => <div key={label} className="rounded-xl border border-slate-200 bg-white px-3 py-3"><p className="text-xs text-slate-500">{label}</p><p className={`mt-1 text-2xl font-black ${color}`}>{value}</p></div>)}</div>
    </section>
    {conditions.length ? <section className="rounded-xl border border-slate-200 bg-slate-50/70 p-4" aria-label="前置条件结果">
      <div className="flex items-center justify-between gap-3"><h3 className="font-bold text-slate-900">前置条件</h3><span className="text-xs text-slate-500">三项要求按顺序检查</span></div>
      <ol className="mt-3 grid gap-2 md:grid-cols-3">{conditionOrder.map((id, i) => { const row = conditions.find(item => String(item.id) === id) || {}; const passed = row.passed === true; const skipped = row.status === 'skipped'; return <li key={id} className={`rounded-lg border bg-white p-3 ${passed ? 'border-emerald-200' : skipped ? 'border-slate-200' : 'border-rose-300'}`}><div className="flex items-start gap-2"><span className={`flex size-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold ${passed ? 'bg-emerald-100 text-emerald-700' : skipped ? 'bg-slate-100 text-slate-500' : 'bg-amber-100 text-amber-700'}`}>{i + 1}</span><div className="min-w-0"><p className="font-medium text-slate-900">{labels[id]}</p><p className={`mt-1 text-xs font-semibold ${passed ? 'text-emerald-700' : skipped ? 'text-slate-500' : 'text-rose-700'}`}>{passed ? '已通过' : skipped ? '未检查' : '未通过'}</p></div></div><details className="mt-2 text-xs text-slate-600"><summary className="cursor-pointer text-slate-500">查看说明</summary><p className="mt-2 leading-5">{String(row.reason || '')}</p>{!passed ? <p className="mt-2 rounded-md bg-amber-50 p-2 text-amber-800">修改建议：{String(row.suggestion || fixedSuggestions[id])}</p> : null}</details></li>; })}</ol>
      {conditions.some(row => row.passed !== true) ? <p className="mt-3 text-xs text-amber-800">前置校验未全部通过，本次未执行正式数值一致性核验。</p> : null}
    </section> : null}
    {prerequisitesPassed && results.length ? <section aria-label="数值型论点核验列表">
      <div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="font-bold text-slate-900">逐项论点核验</h3><p className="mt-1 text-xs text-slate-500">默认优先显示需要人工关注的论点。</p></div><div className="flex flex-wrap gap-1 rounded-lg bg-slate-100 p-1">{([['attention', '需关注'], ['all', '全部'], ['inconsistent', '不一致'], ['inconclusive', '无法确定'], ['consistent', '一致']] as const).map(([value, label]) => <button type="button" key={value} className={`rounded-md px-2 py-1 text-xs ${filter === value ? 'bg-white font-semibold text-brand-700 shadow-sm' : 'text-slate-500 hover:text-slate-800'}`} onClick={() => setFilter(value)}>{label}</button>)}</div></div>
      <div className="mt-3 space-y-3">{visibleResults.length ? visibleResults.map((row, i) => {
        const status = statusOf(row);
        const declaration = row.declaration as Row | undefined;
        const mapping = mappings.find(m => m.declaration_id === row.declaration_id);
        const contribution = contributions.find(c => c.id === declaration?.contribution_id);
        const findingKey = findings.find(item => item.finding.finding_id === `${run.rule_id}_${row.declaration_id}`)?.key;
        const abstractAnchors = objects(row.abstract_anchors);
        const evidence = objects(row.evidence);
        const evidenceAnchors = objects(row.evidence_anchors);
        return <article className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm" key={String(row.declaration_id || i)}>
          <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-wide text-slate-400">论点 {i + 1}</p><h4 className="mt-1 text-base font-bold text-slate-950">{String(declaration?.text || row.declaration_id || '未提供论点文本')}</h4></div><span className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${statusTone(status)}`}>{statusLabel(status)}</span></div>
          <div className="mt-4 grid gap-3 lg:grid-cols-2">
            <div className="rounded-lg bg-slate-50 p-3"><p className="text-xs font-semibold text-slate-500">摘要数值论点</p>{abstractAnchors.length ? abstractAnchors.map((anchor, index) => <EvidenceButton key={index} label="摘要数值论点" page={pageNumber((anchor.location as Row)?.page_number)} findingKey={findingKey} anchorId={String(anchor.anchor_id || `abstract-${row.declaration_id}`)} />) : <p className="mt-2 text-xs text-slate-500">暂无摘要定位</p>}</div>
            <div className="rounded-lg bg-slate-50 p-3"><p className="text-xs font-semibold text-slate-500">实验结果证据</p>{evidence.length ? evidence.map((e, index) => { const anchorId = String(e.candidate_id || e.id || ''); const anchor = evidenceAnchors.find((candidate) => String(candidate.anchor_id || '') === anchorId); const anchorLocation = anchor?.location as Row | undefined; return <EvidenceButton key={index} label="实验结果证据" page={pageNumber(anchorLocation?.page_number ?? e.page)} findingKey={findingKey} anchorId={anchorId} />; }) : <p className="mt-2 text-xs text-slate-500">暂无实验结果定位</p>}</div>
          </div>
          <dl className="mt-4 grid gap-2 text-xs text-slate-600 sm:grid-cols-3"><div><dt className="text-slate-400">研究贡献</dt><dd className="mt-1 text-slate-700">{String(contribution?.text || declaration?.contribution_id || '—')}</dd></div><div><dt className="text-slate-400">研究章节</dt><dd className="mt-1 text-slate-700">{String(mapping?.chapter_title || mapping?.chapter_id || '—')}</dd></div><div><dt className="text-slate-400">实验子章节</dt><dd className="mt-1 text-slate-700">{Array.isArray(mapping?.experiment_titles) ? mapping.experiment_titles.join('、') : Array.isArray(mapping?.experiment_section_ids) ? mapping.experiment_section_ids.join('、') : '—'}</dd></div></dl>
          <div className="mt-4 border-t border-slate-100 pt-3"><p className="text-xs font-semibold text-slate-500">判断依据</p><p className="mt-1 leading-6 text-slate-700">{String(row.reason || '未提供')}</p>{row.suggestion ? <p className="mt-2 rounded-lg bg-blue-50 p-3 text-sm leading-6 text-blue-900"><strong>修改建议：</strong>{String(row.suggestion)}</p> : null}</div>
        </article>;
      }) : <p className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">当前筛选下没有论点。</p>}</div>
    </section> : <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">当前没有可核验的数值型论点。</div>}
    {!prerequisitesPassed ? <p className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm font-semibold text-rose-700">前置条件未全部通过，未执行逐项数值核验。</p> : null}
    {trace?.run_id ? <p className="text-xs text-slate-400">检测记录：{String(trace.run_id)}</p> : null}
  </div>;
}
