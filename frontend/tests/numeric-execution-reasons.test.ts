import { describe, it, expect } from 'vitest';
import { numericExecutionWarnings } from '../src/components/paperLint/model';
import type { PaperLintRuleRun } from '../src/api/paperLint';
import { REVIEW_COPY } from '../src/i18n/review-copy.js';

const failed = (params: Record<string, unknown> = {}): PaperLintRuleRun => ({
 rule_run_id:'numeric',rule_id:'abstract_numeric_consistency_check',severity:'warning',
 execution_status:'error',outcome:'inconclusive',evidence_mode:'derived',findings:[],params,
} as PaperLintRuleRun);

describe('numeric execution warnings report only supported causes',()=>{
 it('a real chapter mapping ContractError is not presented as API congestion',()=>{
  const warning=numericExecutionWarnings(failed({failure:{error_type:'ContractError',message:'experiment is not a descendant of chapter'}}))[0];
  expect(warning.reason).toContain('章节');expect(warning.reason).toContain('对应关系');
  expect(warning.reason).not.toMatch(/人数|繁忙|请求限制/);
 });
 it('invalid numerical output is a validation failure',()=>{
  const warning=numericExecutionWarnings(failed({failure:{error_type:'ContractError',message:'invalid numeric value'}}))[0];
  expect(warning.reason).toContain('校验');expect(warning.reason).not.toMatch(/人数|繁忙/);
 });
 it('a shared-slot timeout reports timeout without inventing its cause',()=>{
  const warning=numericExecutionWarnings(failed({failure:{error_type:'TimeoutError',message:'campus API request timed out waiting for a shared slot'}}))[0];
  expect(warning.reason).toContain('超时');expect(warning.reason).not.toMatch(/人数|繁忙|请求限制/);
 });
 it('an explicit HTTP 429 can report a request restriction',()=>{
  const warning=numericExecutionWarnings(failed({failure:{error_type:'HTTPError',message:'HTTP Error 429: Too Many Requests'}}))[0];
  expect(warning.reason).toContain('请求限制');expect(warning.reason).not.toContain('人数');
 });
 it('an upstream service failure is distinct from a request restriction',()=>{
  const warning=numericExecutionWarnings(failed({failure:{error_type:'HTTPError',message:'HTTP Error 503: Service Unavailable'}}))[0];
  expect(warning.reason).toContain('暂不可用');expect(warning.reason).not.toMatch(/人数|请求限制/);
 });
 it('unknown and old errors use a neutral explanation and keep the input immutable',()=>{
  const input=failed(),snapshot=structuredClone(input);
  const warnings=numericExecutionWarnings(input);
  expect(warnings[0].reason).not.toMatch(/人数|繁忙|请求限制|超时/);
  expect(warnings[0].reason).toContain('未完成');expect(input).toEqual(snapshot);
  expect(warnings[0].feedbackTarget?.key).toBeTruthy();
 });
 it('a normally inapplicable rule and prerequisite descriptions stay unchanged',()=>{
  const input={...failed(),execution_status:'completed',outcome:'not_applicable'} as PaperLintRuleRun;
  expect(numericExecutionWarnings(input)).toEqual([]);
  const condition={id:'experiment_subsection',passed:false,reason:'原前置条件说明',suggestion:''};
  const warning=numericExecutionWarnings({...input,outcome:'inconclusive',params:{preconditions:[condition]}})[0];
  expect(warning.reason).toBe('原前置条件说明');expect(warning.preconditionId).toBe('experiment_subsection');
 });
 it('every new cause-specific explanation has reviewed English copy',()=>{
  for(const failure of [undefined,{error_type:'ContractError',message:'experiment is not a descendant of chapter'},{error_type:'ContractError',message:'invalid numeric value'},{error_type:'TimeoutError',message:'request timed out'},{error_type:'HTTPError',message:'HTTP Error 429: Too Many Requests'},{error_type:'HTTPError',message:'HTTP Error 503: Service Unavailable'}]){
   const warning=numericExecutionWarnings(failed(failure?{failure}:{}))[0];
   const translated=REVIEW_COPY[warning.reason as keyof typeof REVIEW_COPY];
   expect(typeof translated).toBe('string');expect(translated).not.toMatch(/[\u3400-\u9fff]/);
  }
 });
});
