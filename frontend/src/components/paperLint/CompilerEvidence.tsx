import type { CompilerDiagnostic, PaperLintEvidence, PaperLintBasis } from '../../api/paperLint';
const MAX_VISIBLE_EVIDENCE_CHARS = 320;

function visibleEvidenceQuote(value?: string | null) {
  if (!value) return null;
  const text = String(value);
  return text.length > MAX_VISIBLE_EVIDENCE_CHARS
    ? `${text.slice(0, MAX_VISIBLE_EVIDENCE_CHARS)}…（完整证据已保留用于修复建议）`
    : text;
}

function publicUrl(value?: string | null) {
  try { const url = new URL(value || ''); return url.protocol === 'https:' && !url.username && !url.password ? url.href : null; } catch { return null; }
}
export function EvidenceLinks({ items, basis }: { items: PaperLintEvidence[]; basis?: PaperLintBasis[] }) {
  return <div className="mt-2 space-y-2 text-xs text-slate-600">{basis?.map(item => <div key={item.id} className="rounded bg-slate-50 p-2"><strong>{item.kind === 'standard' ? '标准依据' : '项目规则依据'}</strong><p>{item.id}</p>{item.text ? <p className="whitespace-pre-wrap break-words">{item.text}</p> : null}</div>)}{items.map((item, index) => {
    const url = publicUrl(item.url);
    return <div key={`${item.id}-${index}`}>{url ? <a href={url} target="_blank" rel="noopener noreferrer" className="text-brand-700 underline" onClick={event => event.stopPropagation()}>{item.provider || '外部证据'}</a> : null}
      {item.quote ? <p className="mt-1 whitespace-pre-wrap break-words">{visibleEvidenceQuote(item.quote)}</p> : null}</div>;
  })}</div>;
}
export function CompilerDiagnostics({ items }: { items?: CompilerDiagnostic[] }) {
  if (!items?.length) return null;
  const notFound = items.filter(item => item.kind === 'serpapi_not_found');
  const other = items.filter(item => item.kind !== 'serpapi_not_found');
  return <div className="mt-2 space-y-2 text-xs text-slate-600">
    {notFound.length ? <div className="rounded-lg border border-blue-200 bg-blue-50 p-3">
      <strong className="text-blue-900">检索提示：未在 SerpAPI 中查到（{notFound.length} 条）</strong>
      <p className="mt-1 text-blue-800">这些条目不计入规则警告，也不会生成 AI 修复建议；请人工核对题名、作者或 DOI。</p>
      <ul className="mt-2 list-disc space-y-1 pl-4 text-blue-900">
        {notFound.slice(0, 100).map((item, index) => <li key={`${item.node_id}-${index}`}>{item.message || '未在 SerpAPI 中查到该参考文献'}</li>)}
      </ul>
      {notFound.length > 100 ? <p className="mt-1">此处展示前 100 项，完整记录保存在检测报告中。</p> : null}
    </div> : null}
    {other.length ? <details className="text-xs text-slate-600"><summary className="cursor-pointer">证据不足或运行异常：{other.length} 项</summary>
      <div className="mt-2 max-h-72 space-y-3 overflow-auto">{other.slice(0, 100).map((item, index) => <div key={`${item.node_id}-${item.check_id}-${index}`}>
        <strong>{item.status === 'UNKNOWN' ? '无法判定' : '运行异常'}</strong>
        <p>{item.message || item.reasons.join('；') || '当前证据不足以得出结论。'}</p><EvidenceLinks items={item.evidence} basis={item.basis_details} />
      </div>)}{other.length > 100 ? <p>此处展示前 100 项，完整记录保存在检测报告中。</p> : null}</div></details> : null}
  </div>;
}
