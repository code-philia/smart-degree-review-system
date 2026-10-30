import type { PaperLintRuleRun } from '../../api/paperLint';

const labels: Record<string, string> = { abstract_numeric: '摘要研究贡献与数值声明', contribution_mapping: '研究章节映射', experiment_subsection: '下级实验子章节' };
type Row = Record<string, unknown>;
function objects(value: unknown): Row[] {
  return Array.isArray(value) ? value.filter((r): r is Row => Boolean(r && typeof r === 'object')) : [];
}

export function NumericReviewDetails({ run, pdfUrl }: { run: PaperLintRuleRun; pdfUrl?: string }) {
  if (run.rule_id !== 'abstract_numeric_consistency_check') return null;
  const params = run.params || {};
  const conditions = objects(params.preconditions);
  const results = objects(params.numeric_results);
  const mappings = objects(params.mappings);
  const contributions = objects(params.contributions);
  const trace = params.trace as Row | undefined;
  return <div className="mt-3 space-y-3 text-sm" data-testid="numeric-review-details">
    {conditions.length ? <div className="space-y-2 rounded border border-slate-200 p-3">
      <p className="font-semibold">前置条件检查</p>
      {conditions.map((row, i) => <div key={String(row.id || i)}>
        <p>{labels[String(row.id)] || String(row.id)}：{row.passed === true ? '通过' : '未通过'}</p>
        <p className="text-slate-600">{String(row.reason || '')}</p>
        {row.passed !== true && row.suggestion ? <p>调整建议：{String(row.suggestion)}</p> : null}
      </div>)}
    </div> : null}
    {results.map((row, i) => {
      const declaration = row.declaration as Row | undefined;
      const mapping = mappings.find(m => m.declaration_id === row.declaration_id);
      const contribution = contributions.find(c => c.id === declaration?.contribution_id);
      return <div className="space-y-2 rounded border border-violet-200 bg-violet-50 p-3" key={String(row.declaration_id || i)}>
        <p className="font-semibold">{row.status === 'consistent' ? '一致' : row.status === 'inconsistent' ? '不一致' : '无法确定'}</p>
        <p>摘要声明：{String(declaration?.text || row.declaration_id || '')}</p>
        <p className="text-xs text-slate-600">所属贡献：{String(contribution?.text || declaration?.contribution_id || '')} · 研究章节：{String(mapping?.chapter_title || mapping?.chapter_id || '')} · 实验子章节：{Array.isArray(mapping?.experiment_titles) ? mapping.experiment_titles.join('、') : Array.isArray(mapping?.experiment_section_ids) ? mapping.experiment_section_ids.join('、') : ''}</p>
        {objects(row.abstract_anchors).map((a, index) => <p className="text-xs text-slate-600" key={index}>摘要位置：第 {String((a.location as Row)?.page_number || '')} 页</p>)}
        {objects(row.evidence).map((e, index) => <div key={index}>
          <p>正文证据：{String(e.quote || '')}</p>
          {pdfUrl ? <a className="text-brand-700 underline" href={`${pdfUrl}#page=${Number(e.page)}`} target="_blank" rel="noreferrer">查看 PDF 第 {String(e.page)} 页</a> : <p>第 {String(e.page)} 页</p>}
        </div>)}
        <p>判断依据：{String(row.reason || '')}</p>
        {row.suggestion ? <p>核对建议：{String(row.suggestion)}</p> : null}
      </div>;
    })}
    {trace?.run_id ? <p className="text-xs text-slate-500">检测记录：{String(trace.run_id)}</p> : null}
  </div>;
}
