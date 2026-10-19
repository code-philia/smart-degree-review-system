import {describe,it,expect} from 'vitest';
import {compilerPublicationLabel,compilerPublicationSummary} from '../src/components/paperLint/model';
import type {PaperLintRuleRun,PaperLintResult} from '../src/api/paperLint';
const run=(patch:Partial<PaperLintRuleRun>={})=>({rule_run_id:'r',rule_id:'sjtu_rule_31',severity:'warning',execution_status:'completed',outcome:'inconclusive',findings:[],publication_status:'NO_ALERT',...patch}) as PaperLintRuleRun;
const result=(runs:PaperLintRuleRun[],errors=0)=>({rule_runs:runs,summary:{finding_count:0,error_rule_count:errors,unsupported_rule_count:0}}) as PaperLintResult;
describe('confirmed-only compiler wording',()=>{
 it('labels NO_ALERT without compliance or unknown wording',()=>{
  expect(compilerPublicationLabel(run())).toBe('未触发告警');expect(compilerPublicationSummary(result([run()]))).toBe('未触发告警');
 });
 it('keeps execution failure visible and confirmed alerts distinct',()=>{
  expect(compilerPublicationLabel(run({execution_status:'error'}))).toBe('执行失败');
  expect(compilerPublicationSummary(result([run({execution_status:'error'})],1))).toBe('部分规则执行失败');
  expect(compilerPublicationLabel(run({publication_status:'ALERT'}))).toBe('发现问题');
 });
 it('does not relabel the existing local or six-rule results',()=>{
  expect(compilerPublicationLabel(run({rule_id:'sjtu_rule_18'}))).toBeNull();
  expect(compilerPublicationSummary(result([run({rule_id:'sjtu_rule_18'})]))).toBeNull();
 });
});
