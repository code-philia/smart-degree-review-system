import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { FindingsPane } from '../src/components/paperLint/FindingsPane';
import { flattenPaperLintFindings } from '../src/components/paperLint/model';
import { analysisEvidenceDescriptions } from '../src/components/paperLint/analysisEvidence';
import { addTranslations, clearTranslations, setLocale } from '../src/i18n/locale';
import type { PaperLintRuleRun } from '../src/api/paperLint';

const rule='abstract_numeric_consistency_check';
const reason='声明称“仅导致最高8.82%的缺失率”，需在实验数据中核实最高缺失率是否为8.82%。主证据e88描述安全域大小实验，提到sha256和rsa的TLB缺失率均低于0.01%，但未给出具体数值，也未提及8.82%。e94和e145为表格标题，未提供数据。e131提及SP-TLB对比，但未给出具体缺失率数值。e134描述非安全域实验配置，未提供具体数值。e136为定性描述。所有候选证据均未出现8.82%这一数值，且无表格数据可核对。由于证据不足，无法确认或否定该数值，故判定为inconclusive。';
function example():PaperLintRuleRun {
  return {rule_id:rule,rule_run_id:'saved',severity:'info',execution_status:'completed',outcome:'inconclusive',findings:[],params:{numeric_results:[{
    declaration_id:'d2',status:'inconclusive',reason,declaration:{number:'8.82',unit:'%',metric:'缺失率',text:'仅导致最高8.82%的缺失率'},
    evidence:[],evidence_quote:'',evidence_anchors:[],abstract_anchors:[{anchor_id:'abstract-d2',role:'source_span',location:{type:'pdf_page',page_number:7}}],
  }]}};
}
function show(run=example()) {
  const findings=flattenPaperLintFindings({rule_runs:[run]});
  const onFindingClick=vi.fn(),onAnchorClick=vi.fn();
  render(<FindingsPane findings={findings} rules={[]} activeFindingKey={findings[0].key} activeAnchorId={null}
    onFindingClick={onFindingClick} onAnchorClick={onAnchorClick}/>);
  return {findings,onFindingClick,onAnchorClick};
}
beforeEach(()=>{setLocale('zh');clearTranslations();});
afterEach(()=>{setLocale('zh');clearTranslations();});

it('displays every saved candidate description without claiming source text or changing the verdict',()=>{
  const run=example(),before=JSON.stringify(run);
  const {onFindingClick,onAnchorClick}=show(run);
  const area=screen.getByRole('region',{name:'论据'});
  expect(within(area).getAllByTestId('analysis-evidence')).toHaveLength(5);
  for(const description of ['安全域大小实验','表格标题，未提供数据','SP-TLB对比','非安全域实验配置','定性描述']) expect(area).toHaveTextContent(description);
  expect(area).toHaveTextContent('但未给出具体数值，也未提及8.82%');
  expect(area).not.toHaveTextContent(/e88|e94|e145|e131|e134|e136|原分析提及的候选论据|当前报告未保存/);
  expect(within(area).queryByRole('button')).toBeNull();
  fireEvent.click(within(area).getAllByTestId('analysis-evidence')[0]);
  expect(onFindingClick).not.toHaveBeenCalled();expect(onAnchorClick).not.toHaveBeenCalled();
  expect(screen.getByRole('region',{name:'不一致处'})).toHaveTextContent('论据不足');
  expect(JSON.stringify(run)).toBe(before);
});
it('keeps continuation qualifiers and scientific numbers without pulling in the claim or final verdict',()=>{
  const descriptions=analysisEvidenceDescriptions('声明称准确率为88%。主证据d3:e12显示误差1e-3。该结果仅适用于小样本。但尚未覆盖全部设置。候选证据d3:t4为表格标题，没有具体数值。因此无法确认88%。');
  expect(descriptions).toHaveLength(2);
  expect(descriptions[0]).toContain('1e-3');expect(descriptions[0]).toContain('仅适用于小样本');expect(descriptions[0]).toContain('尚未覆盖全部设置');
  expect(descriptions.join('')).not.toMatch(/d3:|88%|因此/);
});
it('does not invent evidence from a claim or an overall no-evidence conclusion',()=>{
  expect(analysisEvidenceDescriptions('声明称模型得分0.88。未找到相关实验依据，无法核实。')).toEqual([]);
});
it('separates described candidates in lists while keeping references with a shared description together',()=>{
  const descriptions=analysisEvidenceDescriptions('声明称比例为1-5%。检查了主证据d3:t1（实验设置描述，未提及建模比例）、d3:t2（吞吐量图，含13%和28%，但未明确为建模比例）、d3:e3、d3:e4（均为文字描述，未给出比例）。所有候选证据均未提供1-5%的数据。');
  expect(descriptions.map(value=>value.replace(/[。；;、]$/,''))).toEqual(['（实验设置描述，未提及建模比例）','（吞吐量图，含13%和28%，但未明确为建模比例）','（均为文字描述，未给出比例）']);
});
it('keeps independent semicolon candidates and their dataset-specific quantities separate',()=>{
  const descriptions=analysisEvidenceDescriptions('检查主证据：d2:e67（第60页）讨论Cyclo-23-TS，但未给出2.5913，仅提及MAE 3.56；d2:e71（第60页）讨论GDB7-22-TS，给出MAE 5.3934，非Cyclo-23-TS；d2:e60（第59页）给出MAE 3.43，但未提粗糙坐标。所有主证据均未出现2.5913。');
  expect(descriptions).toHaveLength(3);
  expect(descriptions[0]).toContain('MAE 3.56');expect(descriptions[0]).not.toContain('5.3934');
  expect(descriptions[1]).toContain('MAE 5.3934，非Cyclo-23-TS');
  expect(descriptions[2]).toContain('MAE 3.43，但未提粗糙坐标');
  expect(descriptions.join('')).not.toMatch(/第\d+页|d2:/);
});
it('removes unverified page mentions from descriptions and continuations without unbalancing parentheses',()=>{
  const descriptions=analysisEvidenceDescriptions('检查主证据：d2:t1（p65表格）和d2:t2（p66表格）均为延迟图，无资源利用率数据；d2:e207（p69段落）提到能耗开销减少51.2%，但这是能耗而非资源利用率。该结果见第70页，尚未与基线对比。候选证据d2:t3（表4.2）未提供数值。');
  expect(descriptions).toHaveLength(3);
  expect(descriptions[0]).toBe('（表格）和（表格）均为延迟图，无资源利用率数据；');
  expect(descriptions[1]).toContain('51.2%，但这是能耗而非资源利用率');
  expect(descriptions[1]).toContain('尚未与基线对比');
  expect(descriptions[2]).toBe('（表4.2）未提供数值。');
  expect(descriptions.join('')).not.toMatch(/p\d+|第\d+页|d2:/);
});
it('keeps stored source evidence ahead of the analysis fallback',()=>{
  const run=example(),row=(run.params!.numeric_results as any[])[0];
  row.evidence=[{candidate_id:'d2:t1',quote:'原文对应实验结果为8.82%。'}];
  row.evidence_anchors=[{anchor_id:'d2:t1',role:'source_span',location:{type:'pdf_page',page_number:11,text_excerpt:'原文对应实验结果为8.82%。'}}];
  show(run);
  const area=screen.getByRole('region',{name:'论据'});
  expect(area).toHaveTextContent('原文对应实验结果为8.82%');
  expect(within(area).queryByTestId('analysis-evidence')).toBeNull();
  expect(within(area).getByRole('button',{name:'查看论据 1 原文'})).toBeVisible();
});
it('uses the current English analysis when translation arrives, without leaking Chinese while waiting',()=>{
  setLocale('en');const {findings}=show();
  let area=screen.getByRole('region',{name:'Evidence'});
  expect(area.textContent).not.toMatch(/安全域|表格标题|SP-TLB对比/);
  act(()=>addTranslations({[findings[0].finding.message]:'The claim states a maximum miss rate of 8.82%. Primary evidence e88 describes the secure domain experiment and reports a miss rate below 0.01%, but does not mention 8.82%. Evidence e94 and e145 are table headings without data. Therefore, the result is inconclusive.'}));
  area=screen.getByRole('region',{name:'Evidence'});
  expect(area).toHaveTextContent('secure domain experiment');
  expect(area).toHaveTextContent('does not mention 8.82%');
  expect(area).toHaveTextContent('table headings without data');
  expect(area.textContent).not.toMatch(/e88|e94|e145/);
});
