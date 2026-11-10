import {expect,it} from 'vitest';
import type {PaperLintRuleRun} from '../src/api/paperLint';
import {numericDisplayFindings} from '../src/components/paperLint/model';
import {numericDisplayFindings as sharedNumericDisplayFindings} from '../../shared/paper-lint-presentation.mjs';

function fixture(status:string):PaperLintRuleRun {
  return {rule_id:'abstract_numeric_consistency_check',rule_run_id:'numeric',severity:'warning',
    execution_status:'completed',outcome:'issues_found',findings:[],params:{preconditions:[{passed:true}],numeric_results:[{
      declaration_id:'d1',status,reason:'D1:A1在第12页与摘要数值不一致。',suggestion:'请核对原始实验数据。',
      evidence:[{candidate_id:'D1:A1'}],abstract_anchors:[{anchor_id:'abstract',location:{type:'pdf_page',page_number:1,text_excerpt:'摘要原文'}}],
      evidence_anchors:[{anchor_id:'D1:A1',location:{type:'pdf_page',page_number:12,text_excerpt:'实验原文'}}]
    }]}};
}
it.each([['inconsistent','论点与论据不一致','warning'],['inconclusive','论据不明确','info']])(
  'preserves existing Chinese numeric %s presentation and canonical data',(status,prefix,severity)=>{
    const run=fixture(status),before=JSON.stringify(run);
    const findings=numericDisplayFindings(run);
    expect(findings).toHaveLength(1);
    expect(findings[0]).toEqual({
      finding_id:'abstract_numeric_consistency_check_d1',rule_id:'abstract_numeric_consistency_check',
      severity,message:prefix+'：实验结果证据1在与摘要数值不一致。',suggestion:'请核对原始实验数据。',
      anchors:[{anchor_id:'abstract',label:'摘要数值论点',location:{type:'pdf_page',page_number:1,text_excerpt:'摘要原文'}},
        {anchor_id:'D1:A1',label:'实验结果证据1',location:{type:'pdf_page',page_number:12,text_excerpt:'实验原文'}}],
      location:{type:'pdf_page',page_number:1,text_excerpt:'摘要原文'}
    });
    expect(JSON.stringify(run)).toBe(before);
  });
it.each(['inconsistent','inconclusive'])('shares exactly the same %s derivation with the backend helper',status=>{
  const run=fixture(status);
  expect(sharedNumericDisplayFindings(run)).toEqual(numericDisplayFindings(run));
});
