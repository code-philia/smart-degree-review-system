import { ArrowUpRight, ChevronDown } from 'lucide-react';
import type { ReactNode } from 'react';
import { ReportProse, useReportProseText } from '../../i18n/ReportProse';
import { getLocale } from '../../i18n/locale';
import { preserveText } from '../../i18n/jsx-runtime';
import type { PaperLintFindingAnchor } from '../../api/paperLint';
import type { PaperLintFindingItem } from './model';
import type { PdfPageLabels } from './pageLabels';
import { Button } from '../ui';
import { objects, text, object, proseText, compositeClaim, claimSummary, assessmentClaim, readableTable, evidencePresentation, type Row } from './numericFindingPresentation';

// This is an extract from the saved explanation, never a new verdict or calculation.
function explanationExcerpt(value: string, status: string) {
  const prose = (status ? value.replace(/^(?:论点与论据不一致|论据不明确)[：:]\s*/, '') : value).trim();
  if (prose.length <= 190 || !['inconsistent', 'inconclusive'].includes(status)) return prose;
  const sentences = prose.split(/(?<=[。！？!?])\s*|(?<=[.!?])\s+(?=[A-Z])/u).filter(Boolean);
  if (sentences.length < 2) return prose;
  const focus = status === 'inconsistent'
    ? /并非|不一致|不相符|冲突|矛盾|不匹配|differs|discrepan|inconsisten|instead|rather than/i
    : /因此|由于|无法|未能|不足以|未覆盖|证据不足|therefore|cannot|unable|insufficient|not.*verif/i;
  const selected = sentences.filter(sentence => focus.test(sentence));
  const specific = selected.filter(sentence => !/判定为\s*(?:inconclusive|inconsistent|consistent)/i.test(sentence));
  // Retain whole sentences, including qualifiers, signs, units and decimal digits.
  const candidates = specific.length ? specific : selected;
  const excerpt = status === 'inconsistent' ? candidates.slice(0, 1) : candidates.slice(-1);
  return (excerpt.length ? excerpt : sentences.slice(-2)).join(' ');
}

/** Extract literal values already present in the source; never calculate a result. */
// Only show an explicit comparison already made by the saved report. No arithmetic.
function savedContrast(analysis: string, value: string, metric: string) {
  const label = metric.match(/^([A-Za-z][A-Za-z0-9@._+-]*)(?:相对提升|提升|得分|分数|准确率)?$/)?.[1];
  if (!value || !label) return null;
  const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const scalar = '[-+]?\\d+(?:\\.\\d+)?(?:[eE][-+]?\\d+)?[%％]?';
  // Require the metric's own before/after pair immediately followed by its explicit
  // saved arithmetic expression. Merely seeing a number elsewhere is insufficient.
  const pattern = new RegExp(`(?<![A-Za-z0-9_])${escaped}(?![A-Za-z0-9_])\\s*(?:从|由)\\s*${scalar}\\s*(?:提升至|升至|增长至|降至)\\s*${scalar}[，,]\\s*相对提升为\\s*([()（）0-9.\\s+*/÷×−-]+)≈(${scalar})[，,]\\s*(?:并非|而非|而不是)\\s*(${scalar})(?=[。；;，,\\s]|$)`, 'g');
  const matches = [...analysis.matchAll(pattern)].filter(match => {
    const prefix = analysis.slice(0, match.index).split(/[。；;]/).at(-1) || '';
    return match[3] === value.replace(/\s/g, '') && !/若|如果|假设|假定|未|没有|尚|不确定|可能|预期|目标/.test(prefix);
  });
  return matches.length === 1 ? { expression: matches[0][1].trim(), reported: `≈${matches[0][2]}`, claimed: matches[0][3] } : null;
}


function EvidenceTable({ table }: { table: NonNullable<ReturnType<typeof readableTable>> }) {
  return <div className="min-w-0 overflow-x-auto rounded-lg border border-slate-200 bg-white">
    {table.caption ? <p className="border-b border-slate-100 px-2.5 py-2 text-xs font-medium leading-5 text-slate-600">{preserveText(table.caption)}</p> : null}
    <table className="w-full border-collapse text-left text-sm font-normal leading-5"><thead className="bg-slate-50 text-xs text-slate-500"><tr>{table.rows[0].map((cell, n) => <th key={n} className="px-2.5 py-1.5 font-normal">{preserveText(cell)}</th>)}</tr></thead>
      <tbody className="text-slate-700">{table.rows.slice(1).map((cells, n) => <tr key={n} className="border-t border-slate-100">{cells.map((cell, k) => <td key={k} className="px-2.5 py-1.5 tabular-nums">{preserveText(cell)}</td>)}</tr>)}</tbody>
    </table>
  </div>;
}

function Disclosure({ label, children }: { label: string; children: ReactNode }) {
  return <details className="group mt-2 min-w-0 text-xs text-slate-500" onClick={event => event.stopPropagation()}>
    <summary className="flex w-fit max-w-full cursor-pointer list-none items-center gap-1 rounded py-1 font-medium transition-colors hover:text-brand-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500 [&::-webkit-details-marker]:hidden">
      {label}<ChevronDown aria-hidden="true" className="size-3.5 shrink-0 transition-transform group-open:rotate-180" />
    </summary>
    <div className="mt-2 whitespace-normal break-words text-sm leading-6 text-slate-600">{children}</div>
  </details>;
}

function usableSourceAnchor(anchor?: PaperLintFindingAnchor): anchor is PaperLintFindingAnchor {
  return Boolean(anchor?.anchor_id?.trim()) && Number.isInteger(anchor?.location?.page_number) && (anchor?.location?.page_number || 0) > 0;
}

function SourceRegion({ anchor, name, itemKey, onAnchorClick, className = '', children }: {
  anchor?: PaperLintFindingAnchor; name: string; itemKey: string; onAnchorClick: Props['onAnchorClick'];
  className?: string; children: ReactNode;
}) {
  const navigable = usableSourceAnchor(anchor);
  return <div role={navigable ? 'link' : undefined} tabIndex={navigable ? 0 : undefined}
    aria-label={navigable ? name : undefined} title={navigable ? name : undefined}
    className={`${className} ${navigable ? 'cursor-pointer transition-colors hover:border-brand-300 hover:bg-brand-50/60 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500' : 'cursor-default'}`}
    onClick={event => { event.stopPropagation(); if (navigable) onAnchorClick(itemKey, anchor.anchor_id); }}
    onKeyDown={event => {
      event.stopPropagation();
      if (navigable && event.key === 'Enter') { event.preventDefault(); onAnchorClick(itemKey, anchor.anchor_id); }
    }}>
    {children}
  </div>;
}

function SourceLink({ anchor, name, itemKey, pageLabels, locale, onAnchorClick }: {
  anchor?: PaperLintFindingAnchor; name: string; itemKey: string; pageLabels: PdfPageLabels;
  locale: string; onAnchorClick: Props['onAnchorClick'];
}) {
  if (!usableSourceAnchor(anchor)) return null;
  const page = anchor.location.page_number;
  const label = pageLabels[page];
  const pageText = locale === 'en' ? label ? `p. ${label}` : `PDF p. ${page}` : label ? `第 ${label} 页` : `PDF 第 ${page} 页`;
  return <div className="flex max-w-full flex-wrap items-center justify-end gap-x-2 gap-y-1">
    <span className="text-xs font-normal text-slate-400">{pageText}</span>
    <Button type="button" size="sm" variant="secondary" aria-label={name}
      className="border border-brand-200 bg-brand-50 px-2.5 text-xs font-medium text-brand-700 hover:bg-brand-100"
      onClick={event => { event.stopPropagation(); onAnchorClick(itemKey, anchor.anchor_id); }}>
      {name}<ArrowUpRight aria-hidden="true" className="size-3.5 shrink-0" />
    </Button>
  </div>;
}

type Props = {
  item: PaperLintFindingItem;
  sourceLiterals?: readonly string[];
  pageLabels?: PdfPageLabels;
  onAnchorClick: (findingKey: string, anchorId: string) => void;
};

export function NumericFindingContent({ item, sourceLiterals = [], pageLabels = {}, onAnchorClick }: Props) {
  const rows = objects(item.ruleRun.params?.numeric_results);
  const row = rows.find(candidate => text(candidate.declaration_id)
    && item.finding.finding_id === `${item.ruleRun.rule_id}_${text(candidate.declaration_id)}`);
  const declaration = object(row?.declaration);
  const status = text(row?.status) || (/^论点与论据不一致[：:]/.test(item.finding.message) ? 'inconsistent'
    : /^论据不明确[：:]/.test(item.finding.message) ? 'inconclusive' : '');
  const analysis = useReportProseText({ text: item.finding.message, sourceLiterals });
  const locale = getLocale();
  const excerpt = explanationExcerpt(analysis, status);
  const anchors = item.finding.anchors || [];
  const storedEvidence = objects(item.finding.evidence);
  const storedAbstract = storedEvidence.find(entry => text(entry.id).startsWith('abstract-'));
  const abstractAnchor = anchors.find(anchor => anchor.anchor_id.startsWith('abstract-') || /摘要/.test(anchor.label || ''));
  const abstractText = text(declaration.text) || text(abstractAnchor?.location.text_excerpt) || text(storedAbstract?.quote);
  const metric = text(declaration.metric), number = text(declaration.number), unit = text(declaration.unit);
  const value = number ? `${number}${unit ? unit === '%' ? unit : ` ${unit}` : ''}` : '';
  const condition = text(declaration.condition);
  const point = assessmentClaim(locale === 'en' ? analysis : text(row?.reason)) || claimSummary(abstractText, metric, value);
  const composite = compositeClaim(rows,row);
  const candidates = objects(row?.evidence).filter(evidence => text(evidence.quote));
  const storedQuotes = storedEvidence.filter(entry => entry !== storedAbstract && text(entry.quote));
  const legacyEvidence = anchors.filter(anchor => anchor !== abstractAnchor)
    .map(anchor => ({ quote: anchor.location.text_excerpt || '', candidate_id: anchor.anchor_id }));
  const matchingQuoteAnchor = anchors.find(anchor => anchor !== abstractAnchor && text(anchor.location.text_excerpt) === text(row?.evidence_quote));
  const evidence: Row[] = candidates.length ? candidates : text(row?.evidence_quote)
    ? [{ quote: row!.evidence_quote, candidate_id: matchingQuoteAnchor?.anchor_id || '' }] : storedQuotes.length ? storedQuotes : legacyEvidence;
  const primaryEvidenceAnchor = evidence.map(entry => anchors.find(anchor => anchor !== abstractAnchor
    && anchor.anchor_id === text(entry.candidate_id || entry.id))).find(usableSourceAnchor);
  const usedAnchorIds = new Set(evidence.map(entry => text(entry.candidate_id || entry.id)));
  const extraAnchors = anchors.filter(anchor => anchor !== abstractAnchor && !usedAnchorIds.has(anchor.anchor_id));
  const note = status === 'inconsistent' ? '不一致' : status === 'inconclusive' ? '论据不足' : '原判定说明';
  const contrast = status === 'inconsistent' ? savedContrast(analysis, value, metric) : null;
  const linkProps = { itemKey: item.key, pageLabels, onAnchorClick, locale };

  return <div data-testid="numeric-finding-content" className="mt-4 min-w-0 space-y-5 text-sm">
    <section aria-label="论点" className="min-w-0">
      <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
        <h4 className="text-sm font-semibold text-slate-800">论点</h4>
        <SourceLink {...linkProps} anchor={abstractAnchor} name={locale === 'en' ? 'View claim source' : '查看论点原文'} />
      </div>
      <SourceRegion {...linkProps} anchor={abstractAnchor} name={locale === 'en' ? 'View claim source' : '查看论点原文'} className="mt-2.5 rounded-xl border border-slate-200 bg-slate-50/50 px-3.5 py-3">
      {composite ? <>
        <p className="mb-2 text-sm leading-6 text-slate-800">{preserveText(`${composite.metric}（${composite.unit}）`)}</p>
        <div className="overflow-x-auto"><table className="w-full border-collapse text-left text-sm leading-6"><thead className="text-xs text-slate-500"><tr><th className="py-1.5 pr-2 font-normal">方法</th>{composite.scopes.map(scope=><th key={scope} className="px-2 py-1.5 font-normal">{preserveText(scope)}</th>)}</tr></thead><tbody>{composite.methods.map((method,i)=><tr key={method} className="border-t border-slate-200/70"><th className="py-2 pr-2 font-normal text-slate-700">{preserveText(method)}</th>{composite.values[i].map((v,k)=><td key={k} className="px-2 py-2 font-medium tabular-nums text-slate-800">{preserveText(v)}</td>)}</tr>)}</tbody></table></div>
      </> : point ? <p className="whitespace-normal break-words text-sm leading-6 text-slate-800">{preserveText(proseText(point))}</p> : metric || value ? <p className="text-sm leading-6 text-slate-800">{preserveText(`${metric} ${value}`)}</p> : <p className="text-sm leading-6 text-slate-500">当前报告未保存独立的论点信息。</p>}
      {!composite && condition && !point.includes(condition) ? <p className="mt-1 text-xs leading-5 text-slate-500">{preserveText(condition)}</p> : null}

      </SourceRegion>
    </section>

    <section aria-label="论据" className="min-w-0">
      <h4 className="text-sm font-semibold text-slate-800">论据</h4>
      <div className="mt-2.5 rounded-xl border border-slate-200 bg-slate-50/50 px-3.5 py-3">
      {evidence.length ? <div className="space-y-3.5">{evidence.map((entry, index) => {
        const quote = text(entry.quote);
        const anchorId = text(entry.candidate_id || entry.id);
        const anchor = anchors.find(candidate => candidate.anchor_id === anchorId && candidate !== abstractAnchor);
        const { table, largeTable, unclear, values, focusedTable, cell, visibleQuote } = evidencePresentation(
          quote, metric, text(declaration.method), text(row?.reason), Boolean(composite), analysis, index);

        return <div key={`${anchorId}-${index}`} className="min-w-0 border-b border-slate-100 pb-3 last:border-b-0 last:pb-0">
          <div className="mb-1 flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
            <p className="text-xs font-normal text-slate-500">{locale === 'en' ? `Evidence ${index + 1}` : `论据 ${index + 1}`}</p>
            <SourceLink {...linkProps} anchor={anchor} name={locale === 'en' ? `View evidence ${index + 1} source` : `查看论据 ${index + 1} 原文`} />
          </div>
          <SourceRegion {...linkProps} anchor={anchor} name={locale === 'en' ? `View evidence ${index + 1} source` : `查看论据 ${index + 1} 原文`} className="-mx-1 rounded-lg px-1">
          {focusedTable ? <div className="mt-2"><EvidenceTable table={focusedTable} /></div> : values ? <div className="mt-2 rounded-lg bg-slate-50 px-3 py-2.5"><span className="sr-only">原文数据</span>
            <p className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-sm leading-6 text-slate-700">{preserveText(values.label)}<span className="text-lg font-semibold text-slate-900 tabular-nums">{preserveText(values.before)}</span><span className="text-slate-400"><span className="sr-only">{locale === 'en' ? 'to' : '至'}</span><span aria-hidden="true">→</span></span><span className="text-lg font-semibold text-slate-900 tabular-nums">{preserveText(values.after)}</span></p>
          <p className="mt-1 text-xs leading-5 text-slate-500">{preserveText(visibleQuote)}</p></div> : cell ? <div className="mt-2 rounded-lg bg-slate-50 px-3 py-2.5"><p className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-sm text-slate-700">{preserveText(metric)}<span className="text-lg font-semibold text-slate-900 tabular-nums">{preserveText(cell.value)}</span></p><p className="mt-1 text-xs leading-5 text-slate-500">{preserveText(`${table!.caption ? `${table!.caption} · ` : ''}${cell.method}`)}</p></div>
          : unclear || largeTable ? <p className="mt-2 text-sm leading-6 text-slate-500">此论据是图表，请查看原文。</p>
          : table ? <div className="mt-2"><EvidenceTable table={table} /></div>
          : <p className="mt-2 whitespace-normal break-words text-sm leading-6 text-slate-600">{preserveText(proseText(visibleQuote))}</p>}
          </SourceRegion>
        </div>;
      })}</div> : <p className="mt-2 text-sm leading-6 text-slate-500">当前报告未保存可展示的论据摘录。</p>}
      {extraAnchors.length ? <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1"><span className="text-xs text-slate-400">其他已存定位</span>{extraAnchors.map((anchor,index) => <SourceLink key={anchor.anchor_id} {...linkProps} anchor={anchor} name={locale === 'en' ? `View additional evidence source ${index + 1}` : `查看其他论据定位 ${index + 1}`} />)}</div> : null}
      </div>
    </section>

    <section aria-label="不一致处" className="min-w-0">
      <h4 className="text-sm font-semibold text-slate-800">不一致处</h4>
      <div className="mt-2.5 rounded-xl border border-slate-200 bg-slate-50/50 px-3.5 py-3">
      <SourceRegion {...linkProps} anchor={primaryEvidenceAnchor} name={locale === 'en' ? 'View related evidence source' : '查看相关论据原文'} className="-mx-1 rounded-lg px-1">
      <p><span className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${status === 'inconsistent' ? 'bg-rose-50 text-rose-700' : status === 'inconclusive' ? 'bg-amber-50 text-amber-800' : 'bg-slate-100 text-slate-600'}`}>{note}</span></p>
      {contrast ? <>
        <div role="group" aria-label="数值对照" className="mt-3 space-y-2 rounded-lg border border-slate-200 bg-white p-3">
          <p className="flex flex-wrap items-baseline gap-x-2 text-sm text-slate-700"><span>摘要声明</span><strong className="font-semibold tabular-nums text-slate-900">{preserveText(contrast.claimed)}</strong></p>
          <p className="text-xs text-slate-500">原检测采用的计算</p>
          <p className="break-words font-mono text-sm leading-6 text-slate-800">{preserveText(contrast.expression)}<span className="font-semibold text-rose-700">{preserveText(contrast.reported)}</span></p>
        </div>
        <p className="mt-2 text-sm leading-6 text-slate-700">原检测将该计算结果与摘要数值比较，判定为不一致。</p>
      </> : <p className="mt-2 whitespace-normal break-words text-sm leading-6 text-slate-700">{preserveText(excerpt)}</p>}
      </SourceRegion>
      {contrast || excerpt !== analysis ? <Disclosure label="查看完整分析">{preserveText(analysis)}</Disclosure> : null}
      </div>
    </section>

    {item.finding.suggestion ? <Disclosure label="修改建议"><ReportProse text={item.finding.suggestion} sourceLiterals={sourceLiterals} /></Disclosure> : null}
  </div>;
}
