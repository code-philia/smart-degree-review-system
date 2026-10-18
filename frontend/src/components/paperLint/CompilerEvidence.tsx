import type { CompilerDiagnostic, PaperLintEvidence } from '../../api/paperLint';
function publicUrl(value?: string | null) {
  try { const url = new URL(value || ''); return url.protocol === 'https:' && !url.username && !url.password ? url.href : null; } catch { return null; }
}
export function EvidenceLinks({ items }: { items: PaperLintEvidence[] }) {
  return <div className="mt-2 space-y-2 text-xs text-slate-600">{items.map((item, index) => {
    const url = publicUrl(item.url);
    return <div key={`${item.id}-${index}`}>{url ? <a href={url} target="_blank" rel="noopener noreferrer" className="text-brand-700 underline" onClick={event => event.stopPropagation()}>{item.provider || '外部证据'}</a> : null}
      {item.quote ? <p className="mt-1 whitespace-pre-wrap break-words">{item.quote}</p> : null}</div>;
  })}</div>;
}
export function CompilerDiagnostics({ items }: { items?: CompilerDiagnostic[] }) {
  if (!items?.length) return null;
  return <details className="mt-2 text-xs text-slate-600"><summary className="cursor-pointer">证据不足或运行异常：{items.length} 项</summary>
    <div className="mt-2 max-h-72 space-y-3 overflow-auto">{items.slice(0, 100).map((item, index) => <div key={`${item.node_id}-${item.check_id}-${index}`}>
      <strong>{item.status === 'UNKNOWN' ? '无法判定' : '运行异常'}</strong>
      <p>{item.reasons.join('；') || '当前证据不足以得出结论。'}</p><EvidenceLinks items={item.evidence} />
    </div>)}{items.length > 100 ? <p>此处展示前 100 项，完整记录保存在检测报告中。</p> : null}</div></details>;
}
