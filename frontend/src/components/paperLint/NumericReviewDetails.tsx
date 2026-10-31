import type { PaperLintRuleRun } from '../../api/paperLint';

const conditionOrder = ['abstract_numeric', 'contribution_mapping', 'experiment_subsection'];
const labels: Record<string, string> = { abstract_numeric: '摘要中存在可核验的数值声明', contribution_mapping: '数值声明已映射到研究贡献', experiment_subsection: '数值声明已映射到实验子章节' };
const fixedSuggestions: Record<string, string> = {
  abstract_numeric: '请在摘要中补充可与正文实验结果对应的明确数值、指标和条件；如果摘要本身没有数值声明，则无需进行这项一致性核验。',
  contribution_mapping: '请将每个数值型研究结论明确关联到摘要中的具体方法或研究贡献，避免只给出孤立的数字。',
  experiment_subsection: '请在对应研究章节下组织实验设置、评估或结果小节，并确保数值声明能够映射到真实实验依据。',
};
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
    {conditions.length ? <div className="rounded border border-slate-200 p-3">
      <p className="font-semibold">三项前置条件</p>
      <ol className="mt-3 space-y-0">
        {conditionOrder.map((id, i) => {
          const row = conditions.find(item => String(item.id) === id) || {};
          const skipped = row.status === 'skipped';
          const passed = row.passed === true;
          const status = passed ? '通过' : skipped ? '未检查' : '未通过';
          const tone = passed ? 'border-emerald-500 bg-emerald-50 text-emerald-800' : skipped ? 'border-slate-300 bg-slate-50 text-slate-600' : 'border-amber-500 bg-amber-50 text-amber-900';
          return <li className="relative flex gap-3 pb-4 last:pb-0" key={id}>
            {i < conditionOrder.length - 1 ? <span className="absolute left-3 top-7 h-full w-px bg-slate-200" aria-hidden="true" /> : null}
            <span className={`relative z-10 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-xs font-semibold ${tone}`}>{i + 1}</span>
            <div className="min-w-0 flex-1">
              <p className="font-medium">{labels[id]}：{status}</p>
              <p className="text-slate-600">{String(row.reason || '')}</p>
              {!passed ? <p className="text-amber-800">修改建议：{String(row.suggestion || fixedSuggestions[id])}</p> : null}
            </div>
          </li>;
        })}
      </ol>
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
