import type { PaperLintRuleRun } from '../../api/paperLint';
import type { ReportBlock } from './model';

type Row = Record<string, unknown>;
const rows = (value: unknown): Row[] =>
  Array.isArray(value) ? value.filter((item): item is Row => Boolean(item && typeof item === 'object')) : [];
const text = (value: unknown) => (typeof value === 'string' || typeof value === 'number' ? String(value) : '');
const labels: Record<string, string> = {
  abstract_numeric: '摘要中存在可核验的数值型论点',
  contribution_mapping: '数值型论点已映射到研究贡献',
  experiment_subsection: '数值型论点已映射到实验子章节',
};
const defaultSuggestions: Record<string, string> = {
  abstract_numeric:
    '请在摘要中补充可与正文实验结果对应的明确数值、指标和条件；如果摘要本身没有数值型论点，则无需进行这项一致性核验。',
  contribution_mapping: '请将每个数值型研究结论明确关联到摘要中的具体方法或研究贡献，避免只给出孤立的数字。',
  experiment_subsection: '请在对应研究章节下组织实验设置、评估或结果小节，并确保数值型论点能够映射到真实实验依据。',
};

export function numericReportBlocks(run: PaperLintRuleRun): ReportBlock[] {
  if (run.rule_id !== 'abstract_numeric_consistency_check') return [];
  const params = run.params || {},
    conditions = rows(params.preconditions),
    results = rows(params.numeric_results);
  const blocks: ReportBlock[] = [{ kind: 'subheading', text: '摘要数值型论点核验' }];
  for (const condition of conditions) {
    blocks.push({
      kind: 'text',
      text: `${labels[text(condition.id)] || text(condition.id)}：${condition.passed === true ? '已通过' : condition.status === 'skipped' ? '未检查' : '未通过'}`,
    });
    if (condition.reason) blocks.push({ kind: 'text', text: text(condition.reason) });
    const suggestion =
      text(condition.suggestion) || (condition.passed !== true ? defaultSuggestions[text(condition.id)] : '');
    if (suggestion) blocks.push({ kind: 'text', text: `修改建议：${suggestion}` });
  }
  if (!conditions.length || conditions.some((condition) => condition.passed !== true)) {
    blocks.push({ kind: 'text', text: '前置条件未全部通过，未执行逐项数值核验。' });
    return blocks;
  }
  blocks.push({
    kind: 'meta',
    text: `共核验 ${results.length} 项论点；一致 ${results.filter((row) => row.status === 'consistent').length} 项；不一致 ${results.filter((row) => row.status === 'inconsistent').length} 项；论据不明确 ${results.filter((row) => !['consistent', 'inconsistent'].includes(text(row.status))).length} 项。`,
  });
  results.forEach((row, index) => {
    const declaration = (row.declaration || {}) as Row;
    const mapping = rows(params.mappings).find((item) => item.declaration_id === row.declaration_id);
    const contribution = rows(params.contributions).find((item) => item.id === declaration.contribution_id);
    const status = row.status === 'consistent' ? '一致' : row.status === 'inconsistent' ? '不一致' : '论据不明确';
    blocks.push({
      kind: 'subheading',
      text: `论点 ${index + 1}：${text(declaration.text) || text(row.declaration_id)} · ${status}`,
    });
    if (contribution?.text) blocks.push({ kind: 'text', text: `研究贡献：${text(contribution.text)}` });
    if (mapping)
      blocks.push({
        kind: 'text',
        text: `研究章节：${text(mapping.chapter_title) || text(mapping.chapter_id)}；实验子章节：${(Array.isArray(mapping.experiment_titles) ? mapping.experiment_titles : Array.isArray(mapping.experiment_section_ids) ? mapping.experiment_section_ids : []).map(text).join('、')}`,
      });
    for (const anchor of [...rows(row.abstract_anchors), ...rows(row.evidence_anchors)]) {
      const location = (anchor.location || {}) as Row;
      if (location.page_number)
        blocks.push({
          kind: 'meta',
          text: `${text(anchor.label) || '原文定位'}：PDF 第 ${text(location.page_number)} 页`,
        });
      if (location.text_excerpt) blocks.push({ kind: 'quote', text: text(location.text_excerpt) });
    }
    for (const evidence of rows(row.evidence)) {
      if (evidence.page) blocks.push({ kind: 'meta', text: `实验结果证据：PDF 第 ${text(evidence.page)} 页` });
      if (evidence.quote) blocks.push({ kind: 'quote', text: text(evidence.quote) });
    }
    if (row.reason) blocks.push({ kind: 'text', text: `判断依据：${text(row.reason)}` });
    if (row.suggestion) blocks.push({ kind: 'text', text: `修改建议：${text(row.suggestion)}` });
  });
  return blocks;
}
