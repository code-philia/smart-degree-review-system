import { act, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { FindingsPane } from '../src/components/paperLint/FindingsPane';
import { flattenPaperLintFindings } from '../src/components/paperLint/model';
import type { PaperLintRuleRun } from '../src/api/paperLint';
import { addTranslations, clearTranslations, setLocale } from '../src/i18n/locale';

const rule = 'abstract_numeric_consistency_check';
const claim = '指纹定位在三个区域的平均误差分别为3.57 m、3.69 m和3.62 m，传播模型定位分别为3.73 m、4.01 m和3.79 m。';
const quote = '表5-1 空旷区域实验结果\n | 平均误差（m） | 中位数误差（m）\n指纹定位 | 3.57 | 3.38\n传播模型定位 | 3.73 | 3.62';
const reason = '声明包含三个区域的平均误差，当前条件为空旷区域、指纹定位。实验结果证据1显示3.57 m，与摘要第一个数值一致。但另外两个区域的数值未在当前候选证据中出现。因此，仅能核验空旷区域部分，无法确认其他两个区域的数值。';
function location(page: number, text_excerpt: string) { return { type: 'pdf_page', page_number: page, text_excerpt }; }
function example(status = 'inconclusive'): PaperLintRuleRun {
  return { rule_id: rule, rule_run_id: 'saved-numeric-run', severity: 'warning', execution_status: 'completed', outcome: 'inconclusive', findings: [], params: {
    preconditions: [{ id: 'abstract_numeric', passed: true }],
    numeric_results: [{ declaration_id: 'd1', status, reason, suggestion: '请核对相关实验数据。',
      declaration: { id: 'd1', text: claim, number: '3.57', metric: '平均误差', unit: 'm', condition: '空旷区域，指纹定位', method: '指纹定位' },
      evidence: [{ candidate_id: 'd1:t1', quote, page: 53 }],
      abstract_anchors: [{ anchor_id: 'abstract-d1', label: '摘要数值论点', role: 'source_span', location: location(4, claim) }],
      evidence_anchors: [{ anchor_id: 'd1:t1', label: '实验结果证据1', role: 'source_span', location: location(53, quote) }],
    }],
  } };
}
function show(run = example(), active = true) {
  const findings = flattenPaperLintFindings({ rule_runs: [run] });
  const onFindingClick = vi.fn(), onAnchorClick = vi.fn();
  render(<FindingsPane findings={findings} rules={[]} activeFindingKey={active ? findings[0]?.key : null}
    activeAnchorId={null} onFindingClick={onFindingClick} onAnchorClick={onAnchorClick} />);
  return { findings, onFindingClick, onAnchorClick };
}
beforeEach(() => { setLocale('zh'); clearTranslations(); });
afterEach(() => { setLocale('zh'); clearTranslations(); });

it('separates the current claim, saved evidence and discrepancy in a historical finding', () => {
  const run = example(), original = JSON.stringify(run);
  show(run);
  for (const heading of ['论点', '论据', '不一致处']) expect(screen.getByRole('heading', { name: heading })).toBeVisible();
  const point = screen.getByRole('region', { name: '论点' });
  expect(point).toHaveTextContent('3.57 m');
  expect(point).toHaveTextContent('平均误差');
  expect(screen.getByText('论据不足')).toBeVisible();
  expect(screen.getByText('1 项问题')).toBeVisible();
  expect(JSON.stringify(run)).toBe(original);
});

it('places reliable original-text navigation next to each source and stops event bubbling', async () => {
  const { findings, onFindingClick, onAnchorClick } = show();
  const evidenceLink = screen.getByRole('button', { name: '查看论据 1 原文' });
  expect(evidenceLink).toHaveTextContent('查看论据 1 原文');
  await userEvent.click(evidenceLink);
  expect(onAnchorClick).toHaveBeenCalledWith(findings[0].key, 'd1:t1');
  expect(onFindingClick).not.toHaveBeenCalled();
  const source = screen.getByRole('button', { name: '查看论点原文' });
  fireEvent.keyDown(source, { key: 'Enter' });
  expect(onFindingClick).not.toHaveBeenCalled();
  await userEvent.click(source);
  expect(onAnchorClick).toHaveBeenLastCalledWith(findings[0].key, 'abstract-d1');
});

it('keeps the original source button and full saved analysis available', async () => {
  const run = example();
  (run.params!.numeric_results as any[])[0].declaration.text = claim.repeat(4);
  show(run);
  const analysis = screen.getByText('查看完整分析').closest('details')!;
  expect(analysis).not.toHaveAttribute('open');
  expect(screen.getByRole('button',{name:'查看论点原文'})).toBeVisible();
  expect(screen.getByRole('region',{name:'论点'})).not.toHaveTextContent(claim.repeat(4));
  await userEvent.click(screen.getByText('查看完整分析'));
  expect(analysis).toHaveAttribute('open');
  expect(analysis.textContent).toContain(reason);
});

it('uses the exact declaration ID rather than the array position or ID prefix', () => {
  const run = example();
  const rows = run.params!.numeric_results as any[];
  rows.unshift({ ...rows[0], declaration_id: 'd10', status: 'consistent', declaration: { ...rows[0].declaration, number: '4.01', condition: '其他条件' } });
  show(run);
  const point = screen.getByRole('region', { name: '论点' });
  expect(point).toHaveTextContent('3.57 m');
  expect(within(point).queryByText('其他条件')).not.toBeInTheDocument();
});

it('preserves an inconsistent result and its calculation instead of recomputing or clearing it', async () => {
  const run = example('inconsistent');
  const row = (run.params!.numeric_results as any[])[0];
  row.declaration = { text: 'gAUC最高相对提升5.53%。', number: '5.53', unit: '%', metric: 'gAUC相对提升', condition: '公开数据集' };
  row.reason = '声明称最高相对提升5.53%。主证据显示gAUC从0.9494升至0.9743，按原核验计算约2.62%，并非5.53%。因此原判定认为该数值与证据不一致。';
  const original = JSON.stringify(run);
  show(run);
  const discrepancy = screen.getByRole('region', { name: '不一致处' });
  expect(within(discrepancy).getByText('不一致', { exact: true })).toBeVisible();
  expect(discrepancy.textContent).toContain('2.62%');
  expect(JSON.stringify(run)).toBe(original);
});

it('does not invent missing claim/evidence details in an older report', () => {
  const run = { ...example(), params: {}, findings: [{ finding_id: 'legacy', rule_id: rule, message: '原判定说明：请核对实验范围。' }] } as PaperLintRuleRun;
  show(run);
  expect(screen.getByText('当前报告未保存独立的论点信息。')).toBeVisible();
  expect(screen.getByText('当前报告未保存可展示的论据摘录。')).toBeVisible();
  expect(screen.getByText('原判定说明：请核对实验范围。')).toBeInTheDocument();
  expect(screen.queryByText('论据不足')).not.toBeInTheDocument();
});

it('retains legacy source-anchor navigation when separate numeric rows are absent', async () => {
  const original = (example().params!.numeric_results as any[])[0];
  const run = { ...example(), params: {}, findings: [{ finding_id: 'legacy', rule_id: rule, message: '原判定说明。',
    anchors: [...original.abstract_anchors, ...original.evidence_anchors] }] } as PaperLintRuleRun;
  const { findings, onAnchorClick } = show(run);
  await userEvent.click(screen.getByRole('button', { name: '查看论据 1 原文' }));
  expect(onAnchorClick).toHaveBeenCalledWith(findings[0].key, 'd1:t1');
});

it('shows an original-source entry instead of exposing graph extraction artifacts', () => {
  const run = example(), row = (run.params!.numeric_results as any[])[0];
  const noisy = 'Text Tasks | | | 0.91 Exc | |\n'.repeat(40) + 'FINAL ORIGINAL VALUE 0.33';
  row.evidence[0].quote = noisy;
  const original=JSON.stringify(run);
  show(run, false);
  const evidence = screen.getByRole('region', { name: '论据' });
  expect(evidence.textContent).not.toContain('Text Tasks |');
  expect(within(evidence).getByText('此论据是图表，请查看原文。')).toBeVisible();
  expect(screen.getByRole('button', { name: '查看论据 1 原文' })).toBeVisible();
  expect(JSON.stringify(run)).toBe(original);
});

it('localizes labels and excerpts only after the complete analysis translation is ready', () => {
  const { findings } = show();
  act(() => setLocale('en'));
  for (const name of ['Claim', 'Evidence', 'Discrepancy']) expect(screen.getByRole('heading', { name })).toBeVisible();
  const discrepancy = screen.getByRole('region', { name: 'Discrepancy' });
  expect(discrepancy).toHaveTextContent('Insufficient evidence');
  expect(discrepancy).toHaveTextContent('English translation is not ready yet.');
  expect(discrepancy.textContent).not.toContain('无法确认其他两个区域');
  const translated = 'The claim covers three areas. Evidence 1 supports 3.57 m in the open area. However, evidence for the other two areas is missing from this verification. Therefore, the claim cannot be fully verified.';
  act(() => addTranslations({ [findings[0].finding.message]: translated }));
  expect(discrepancy).toHaveTextContent('the claim cannot be fully verified');
  expect(discrepancy.textContent).not.toContain('English translation is not ready yet.');
  expect(screen.getByRole('region', {name:'Claim'}).textContent).toContain(claim.split('，')[0]);
});

it.each([
  ['Pass@1', '11', '%', '该方法可将模型的Pass@1准确率提升11%。'],
  ['F1分数', '6.7', '%', '本方法在F1分数上平均提高了6.7%以上。'],
  ['任务完成时间', '15.3', '%', '本方法使任务完成时间平均缩短了15.3%以上。'],
])('keeps the original direction and bounds of %s visible', (metric, number, unit, statement) => {
  const run = example(), row = (run.params!.numeric_results as any[])[0];
  row.declaration = { text: statement, metric, number, unit };
  show(run);
  expect(within(screen.getByRole('region', { name: '论点' })).getByText(statement)).toBeVisible();
});

it('preserves the saved inconclusive stance in a legacy finding without numeric rows', () => {
  show({ ...example(), params: {}, findings: [{ finding_id:'legacy',rule_id:rule,message:'论据不明确：当前无法核实实验范围。' }] });
  expect(screen.getByText('论据不足')).toBeVisible();
  expect(screen.getByRole('region', { name:'不一致处' })).toHaveTextContent('当前无法核实实验范围');
});

it('distinguishes a legacy abstract quotation from legacy evidence quotations', async () => {
  const original = (example().params!.numeric_results as any[])[0];
  const run = { ...example(), params:{}, findings:[{finding_id:'legacy',rule_id:rule,message:'论据不明确：原范围待核实。',
    evidence:[{id:'abstract-d1',kind:'source_span',quote:claim},{id:'d1:t1',kind:'source_span',quote}],
    anchors:[...original.abstract_anchors,...original.evidence_anchors]}] } as PaperLintRuleRun;
  const {findings,onAnchorClick}=show(run);
  expect(screen.queryByText('当前报告未保存可展示的论据摘录。')).not.toBeInTheDocument();
  const evidence=screen.getByRole('region',{name:'论据'});
  expect(evidence.textContent).not.toContain(claim);
  await userEvent.click(within(evidence).getByRole('button',{name:'查看论据 1 原文'}));
  expect(onAnchorClick).toHaveBeenCalledWith(findings[0].key,'d1:t1');
});

it('shows legacy finding.evidence quotes even without separate numeric rows or anchors', () => {
  const run={...example(),params:{},findings:[{finding_id:'legacy',rule_id:rule,message:'论据不明确：需核对实验。',
    evidence:[{id:'abstract-d1',kind:'source_span',quote:claim},{id:'d1:t1',kind:'source_span',quote}]}]} as PaperLintRuleRun;
  show(run);
  expect(screen.queryByText('当前报告未保存可展示的论据摘录。')).not.toBeInTheDocument();
  expect(screen.getByRole('region',{name:'论据'}).textContent).toContain('3.73');
  expect(screen.getByRole('region',{name:'论据'}).textContent).not.toContain(claim);
});

it('keeps unmatched stored anchor links when a legacy evidence_quote lacks its candidate ID', async () => {
  const run=example(), row=(run.params!.numeric_results as any[])[0];
  row.evidence=[];row.evidence_quote='单独保存的实验引文。';
  const {findings,onAnchorClick}=show(run);
  await userEvent.click(screen.getByRole('button',{name:'查看其他论据定位 1'}));
  expect(onAnchorClick).toHaveBeenCalledWith(findings[0].key,'d1:t1');
});

it('does not turn a long, multi-value cell into an unfolded readable table', () => {
  const run=example(),row=(run.params!.numeric_results as any[])[0];
  row.evidence[0].quote='设备与指标\n类型 | 结果\n'+['A100-FP A100-INT8 SynGPU-FP SynGPU-INT8','1.0 2.0 3.0 4.0 5.0 6.0 7.0 8.0'].join(' | ');
  show(run);
  const evidence=screen.getByRole('region',{name:'论据'});
  expect(within(evidence).queryByRole('table')).not.toBeInTheDocument();
  expect(within(evidence).getByText('此论据是图表，请查看原文。')).toBeVisible();
});

it('summarizes a long cited passage instead of duplicating the page text in the card', () => {
  const run=example(),row=(run.params!.numeric_results as any[])[0];
  const long='这是一段保留实验条件和具体数值的原文证据。'.repeat(35);
  row.evidence[0].quote=long;
  show(run);
  const region=screen.getByRole('region',{name:'论据'});
  expect(region).not.toHaveTextContent(long);
  expect(region.querySelector('details')).toBeNull();
  expect(within(region).getByRole('button',{name:'查看论据 1 原文'})).toBeVisible();
});

it('keeps keyboard focus on an evidence link after the selected anchor changes', async () => {
  const run=example(),findings=flattenPaperLintFindings({rule_runs:[run]});
  function Interactive() {
    const [anchor,setAnchor]=useState<string|null>(null);
    return <FindingsPane findings={findings} rules={[]} activeFindingKey={findings[0].key} activeAnchorId={anchor}
      onFindingClick={()=>{}} onAnchorClick={(_,id)=>setAnchor(id)} />;
  }
  render(<Interactive />);
  const link=screen.getByRole('button',{name:'查看论据 1 原文'});
  await userEvent.click(link);
  expect(link).toHaveFocus();
  expect(screen.getByRole('button',{name:'查看论据 1 原文'})).toBe(link);
});

it.each(['wide','long'])('uses the original PDF for a %s table rather than packing it into a narrow card', kind => {
  const run=example(),row=(run.params!.numeric_results as any[])[0];
  row.evidence[0].quote=kind==='wide'
    ? ['模型',...Array.from({length:8},(_,i)=>`指标${i+1}`)].join(' | ')+'\n'+['方法A',...Array.from({length:8},(_,i)=>String(i+0.1))].join(' | ')
    : '模型 | 得分\n'+Array.from({length:15},(_,i)=>`方法${i} | ${i+0.1}`).join('\n');
  show(run);
  const region=screen.getByRole('region',{name:'论据'});
  expect(within(region).getByText('此论据是图表，请查看原文。')).toBeVisible();
  expect(region.querySelector('details')).toBeNull();
  expect(within(region).getByRole('button',{name:'查看论据 1 原文'})).toBeVisible();
});

it('shows the metric values used in the saved analysis before the relevant source sentence', () => {
  const run=example('inconsistent'),row=(run.params!.numeric_results as any[])[0];
  row.declaration={text:'gAUC相对提升5.53%。',metric:'gAUC相对提升',number:'5.53',unit:'%'};
  row.reason='原核验采用B数据集上gAUC从0.94升至0.96这组数值。';
  row.evidence[0].quote='在A数据集上，gAUC从0.88升至0.89。在B数据集上，DCN的AUC从0.95升至0.97，gAUC从0.94升至0.96。';
  const before=JSON.stringify(run);
  show(run);
  const evidence=screen.getByRole('region',{name:'论据'});
  expect(within(evidence).getByText('0.94',{exact:true})).toBeVisible();
  expect(within(evidence).getByText('0.96',{exact:true})).toBeVisible();
  expect(within(evidence).getByText('在B数据集上，DCN的AUC从0.95升至0.97，gAUC从0.94升至0.96。')).toBeVisible();
  expect(JSON.stringify(run)).toBe(before);
});

it('does not guess which values belong to the claim when several pairs lack a saved association', () => {
  const run=example(),row=(run.params!.numeric_results as any[])[0];
  row.declaration.metric='gAUC相对提升';row.reason='证据尚未核实。';
  row.evidence[0].quote='在A数据集上，gAUC从0.88升至0.89。在B数据集上，gAUC从0.94升至0.96。';
  show(run);
  expect(within(screen.getByRole('region',{name:'论据'})).queryByText('原文数据')).not.toBeInTheDocument();
});

it('shows every evidence entry and its source button without folding', async () => {
  const run=example(),row=(run.params!.numeric_results as any[])[0];
  row.evidence.push({candidate_id:'d1:e2',quote:'另一段完整的实验上下文。',page:54});
  row.evidence_anchors.push({anchor_id:'d1:e2',label:'实验结果证据2',role:'source_span',location:location(54,'另一段完整的实验上下文。')});
  const {onAnchorClick}=show(run);
  const region=screen.getByRole('region',{name:'论据'});
  expect(within(region).getByText('另一段完整的实验上下文。')).toBeVisible();
  expect(within(region).getByRole('button',{name:'查看论据 2 原文'})).toBeVisible();
  expect(within(region).getByText('另一段完整的实验上下文。').closest('details')).toBeNull();
  expect(within(region).queryByText('查看论据 2',{exact:true})).not.toBeInTheDocument();
  await userEvent.click(within(region).getByRole('button',{name:'查看论据 2 原文'}));
  expect(onAnchorClick).toHaveBeenCalledWith(expect.any(String),'d1:e2');
});

it.each([
  ['ECE','ECE从2降至1–1.5。','ECE从2降至1–1.5。'],
  ['F1','F1从900升至1,000。','F1从900升至1,000。'],
  ['AUC','AUC从0.6升至0.8。AUC从0.4升至0.9。','F1从0.6升至0.8。未核实两套AUC结果。'],
  ['AUC/gAUC','AUC从0.6升至0.8，gAUC从0.4升至0.9。','gAUC从0.4升至0.9。'],
  ['AUC','若AUC从0.5升至0.8，则可达到目标；实际最高仅0.6。','AUC从0.5升至0.8是假设。'],
  ['AUC','没有证据支持AUC从0.5升至0.8。','AUC从0.5升至0.8尚未核实。'],
])('retains the original sentence for ambiguous %s values', (metric,source,analysis) => {
  const run=example(),row=(run.params!.numeric_results as any[])[0];
  row.declaration.metric=metric;row.evidence[0].quote=source;row.reason=analysis;
  show(run);
  expect(within(screen.getByRole('region',{name:'论据'})).queryByText('原文数据')).not.toBeInTheDocument();
});

it.each([
  ['AUC','AUC从0.95升至1.04e-2。','1.04e-2'],
  ['F1','F1从90％升至95％。','95％'],
])('preserves complete numeric notation in %s source values', (metric,source,expected) => {
  const run=example(),row=(run.params!.numeric_results as any[])[0];
  row.declaration.metric=metric;row.evidence[0].quote=source;row.reason=source;
  show(run);
  expect(within(screen.getByRole('region',{name:'论据'})).getByText(expected,{exact:true})).toBeVisible();
});


it('keeps the teacher order while making the stored disagreement explicit', () => {
  const run=example('inconsistent'),row=(run.params!.numeric_results as any[])[0];
  row.declaration={text:'gAUC最高相对提升5.53%。',metric:'gAUC相对提升',number:'5.53',unit:'%'};
  row.reason='主证据显示gAUC从0.9494升至0.9743，相对提升为(0.9743-0.9494)/0.9494≈2.62%，并非5.53%。';
  row.evidence[0].quote='在KKBox数据集上，gAUC从0.9494升至0.9743。';
  show(run);
  const card=screen.getByTestId('numeric-finding-content');
  expect(within(card).getAllByRole('heading').map(h=>h.textContent)).toEqual(['论点','论据','不一致处']);
  const comparison=screen.getByRole('group',{name:'数值对照'});
  expect(comparison).toHaveTextContent('5.53%');
  expect(comparison).toHaveTextContent('≈2.62%');
  expect(comparison).toHaveTextContent('原检测采用的计算');
  expect(comparison).toHaveTextContent('(0.9743-0.9494)/0.9494');
  expect(screen.getByText('原检测将该计算结果与摘要数值比较，判定为不一致。')).toBeVisible();
});

it('keeps raw tables and optional suggestions secondary while showing focused values', () => {
  show();
  const region=screen.getByRole('region',{name:'论据'});
  expect(within(region).getByText('3.57 m',{exact:true})).toBeVisible();
  expect(region.querySelector('details')).toBeNull();
  expect(screen.getByText('请核对相关实验数据。').closest('details')).not.toHaveAttribute('open');
});

it('keeps the original explicit contrast separate from an unrelated metric after a semicolon', () => {
 const run=example('inconsistent'),row=(run.params!.numeric_results as any[])[0];
 row.declaration={text:'gAUC相对提升5.53%。',metric:'gAUC相对提升',number:'5.53',unit:'%'};
 row.reason='主证据提到gAUC从0.9494升至0.9743，相对提升为(0.9743-0.9494)/0.9494≈2.62%，并非5.53%；该段还提到AUC相对提升3.49%，但未涉及gAUC的5.53%。';
 row.evidence[0].quote='在KKBox数据集上，AUC 从0.9594 升至0.9754，gAUC 从0.9494 升至0.9743，相对提升分别达3.49%。';
 show(run);
 expect(screen.getByRole('group',{name:'数值对照'})).toHaveTextContent('≈2.62%');
 expect(within(screen.getByRole('region',{name:'论据'})).getByText('0.9494',{exact:true})).toBeVisible();
});


it.each([
 ['AUC','AUC从0.5升至0.8以上。'],
 ['F1','F1从9升至10 ± 2。'],
 ['ECE','ECE从2降至1至1.5。'],
 ['AUC','AUC从0.5升至0.8是预期目标。'],
 ['AUC','计划将AUC从0.5升至0.8。'],
])('keeps bounds and non-factual %s changes in the source context', (metric,source) => {
 const run=example(),row=(run.params!.numeric_results as any[])[0];
 row.declaration.metric=metric;row.reason=source;row.evidence[0].quote=source;
 show(run);
 const region=screen.getByRole('region',{name:'论据'});
 expect(within(region).queryByText('原文数据')).not.toBeInTheDocument();
 expect(within(region).getByText(source)).toBeVisible();
});

it.each([
 'gAUC计算为1,002%，并非5.53%。',
 'gAUC计算为1–2.62%，而非5.53%。',
 'gAUC结果已列出，NDCG的提升为2.62%，而非5.53%。',
 '尚不能确定gAUC的计算结果为2.62%，而非5.53%。',
])('does not turn an ambiguous saved analysis into a scalar discrepancy: %s', analysis => {
 const run=example('inconsistent'),row=(run.params!.numeric_results as any[])[0];
 row.declaration={text:'gAUC最高相对提升5.53%。',metric:'gAUC相对提升',number:'5.53',unit:'%'};
 row.reason=analysis;
 show(run);
 expect(screen.queryByRole('group',{name:'数值对照'})).not.toBeInTheDocument();
 expect(screen.getByRole('region',{name:'不一致处'})).toHaveTextContent(analysis);
});

it('preserves complete qualified headers and percent units', async () => {
 const run=example(),row=(run.params!.numeric_results as any[])[0];
 row.declaration={text:'误差为2.5。',metric:'误差',number:'2.5',method:'方法A'};
 row.evidence[0].quote='方法 | 误差（m）标准差 | 准确率（%）\n方法A | 2.5 | 95%';
 show(run);
 const region=screen.getByRole('region',{name:'论据'});
 expect(within(region).getByText('2.5',{exact:true})).toBeVisible();
 const table=within(region).getByRole('table');
 expect(within(table).getByRole('columnheader',{name:'误差（m）标准差'})).toBeVisible();
 expect(within(table).getByRole('cell',{name:'95%'})).toBeVisible();
 expect(table).not.toHaveTextContent('95% %');
});

it('shows the full compound claim as a compact fact table when the saved reason checks the whole statement', () => {
 const run=example(),base=(run.params!.numeric_results as any[])[0];
 const areas=['空旷区域','自习区域','书架区域'];
 const methods=['指纹定位','传播模型定位'];
 const values=[['3.57','3.69','3.62'],['3.73','4.01','3.79']];
 run.params!.numeric_results=methods.flatMap((method,i)=>areas.map((area,j)=>({ ...base,declaration_id:`d${i*3+j+1}`,status:i+j===0?'inconclusive':'consistent',reason:i+j===0?reason+'由于声明整体包含三个区域，无法完全验证。':'一致。',declaration:{...base.declaration,id:`d${i*3+j+1}`,abstract_span_id:'a1',method,number:values[i][j],condition:`${area}，${method}`} })));
 const original=JSON.stringify(run);
 show(run);
 const point=screen.getByRole('region',{name:'论点'});
 const table=within(point).getByRole('table');
 for (const area of areas) expect(within(table).getByRole('columnheader',{name:area})).toBeVisible();
 for (const value of values.flat()) expect(within(table).getByText(value,{exact:true})).toBeVisible();
 const evidence=screen.getByRole('region',{name:'论据'});
 const focused=within(evidence).getAllByRole('table').find(table=>!table.closest('details'))!;
 expect(focused).toHaveTextContent('3.57');
 expect(focused).toHaveTextContent('3.73');
 expect(screen.getByRole('region',{name:'不一致处'})).toHaveTextContent('无法确认其他两个区域的数值');
 expect(JSON.stringify(run)).toBe(original);
});

it('uses the same standalone heading treatment for all three sections', () => {
 show();
 const headings=['论点','论据','不一致处'].map(name=>screen.getByRole('heading',{name}));
 expect(new Set(headings.map(h=>h.className)).size).toBe(1);
 const section=screen.getByRole('region',{name:'不一致处'});
 expect(section.className).not.toMatch(/bg-|rounded|p-3/);
 expect(headings[2].nextElementSibling).toHaveTextContent('论据不足');
});


it.each([
 ['文本知识问答能力得分','0.33','','文本知识问答能力得分上涨了0.33，多模态能力上涨了0.30。','文本知识问答能力得分上涨了0.33。'],
 ['通信量','85','%','通信量约降低85%，交互轮数约降低80%。','通信量约降低85%。'],
 ['交互轮数','80','%','通信量约降低85%，交互轮数约降低80%。','交互轮数约降低80%。'],
 ['室内信噪比','9','dB','室内信噪比显著提升（由9 dB提升至23 dB），室外环境也有改善。','室内信噪比显著提升（由9 dB提升至23 dB）。'],
 ['调整响应时间','500','ms','实现了≤500ms的调整响应时间，并保证正确性。','实现了≤500ms的调整响应时间。'],
 ['性能提升','1.46','倍','最高可实现1.46倍的性能提升，进一步验证了有效性。','最高可实现1.46倍的性能提升。'],
])('preserves the complete target clause for %s', (metric,number,unit,source,expected) => {
 const run=example(),row=(run.params!.numeric_results as any[])[0];
 row.declaration={text:source,metric,number,unit};
 show(run);
 expect(screen.getByRole('region',{name:'论点'})).toHaveTextContent(expected);
});


it('uses the saved check description for a continuation evidence passage without reproducing the whole page', () => {
 const run=example('inconsistent'),row=(run.params!.numeric_results as any[])[0];
 row.declaration={text:'gAUC最高相对提升5.53%。',metric:'gAUC相对提升',number:'5.53',unit:'%'};
 row.evidence.push({candidate_id:'d1:e2',quote:'和5.53%；同时，DIN在该数据集上AUC和gAUC分别提升3.93%和4.99%。'+ '与本条核验无关的解释段落。'.repeat(30)});
 row.reason='声明称gAUC相对提升5.53%。主证据d1:t1显示原始指标。次证据d1:e2提到DIN在该数据集上gAUC提升4.99%，也未出现5.53%。因此与摘要不一致。';
 const before=JSON.stringify(run);show(run);
 const region=screen.getByRole('region',{name:'论据'});
 expect(region).toHaveTextContent('DIN在该数据集上gAUC提升4.99%');
 expect(region).not.toHaveTextContent('和5.53%');
 expect(region).not.toHaveTextContent('与本条核验无关的解释段落');
 expect(region.querySelector('details')).toBeNull();
 expect(JSON.stringify(run)).toBe(before);
});

it.each([
 ['通信量降低','85','声明称FP-Exp与BEACON对比，通信量降低约85%。'],
 ['交互轮数降低','80','声明称FP-Exp与BEACON对比，交互轮数降低约80%。'],
])('names the current %s check separately for a paired source statement', (metric,number,reason) => {
 const run=example(),row=(run.params!.numeric_results as any[])[0];
 row.declaration={text:'同时使通信量与交互轮数分别降低约85%和80%',metric,number,unit:'%'};
 row.reason=reason;show(run);
 const point=screen.getByRole('region',{name:'论点'});
 expect(point).toHaveTextContent(metric+'约'+number+'%');
 expect(point).not.toHaveTextContent(number==='85'?'约80%':'约85%');
});

it('never matches a 5% declaration to a 15% source value', () => {
 const run=example(),row=(run.params!.numeric_results as any[])[0];
 row.declaration={text:'准确率在数据集A提高了15%，数据集B提高了五个百分点。',metric:'准确率提升',number:'5',unit:'%'};
 show(run);
 expect(screen.getByRole('region',{name:'论点'})).not.toHaveTextContent('15%');
});


it.each([
 '给出Prompt长度16K/32K时加速比4-6倍，但该条件为高命中率下，且未明确为真实多轮对话任务，故不构成反例。',
 '给出相关实验结果，但表格矩阵不完整，无法明确对应fever数据集和GCRP方法。',
])('preserves applicability and attribution conditions in an evidence explanation', description=>{
 const run=example(),row=(run.params!.numeric_results as any[])[0];
 row.evidence[0].quote='完整实验来源段落。';
 row.reason='主证据d1:t1'+description;
 show(run);
 expect(screen.getByRole('region',{name:'论据'})).toHaveTextContent(description);
});
