import { describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const { toCompilerResult } = require('../src/normative/paperCompilerService');
const safeReason = 'isolated program rejected: ZeroDivisionError at <paper-program> lines 2: division by zero';
function report(status='ERROR') {
  return {schema_version:'paper-check/1.0',pipeline_version:'pipeline-v1',runtime:{status:'candidate_rejected',
    report_version:{suite_version:'report-release'},current_snapshot:{freeze:false,generation:7,active_version:'current-release'}},
    rules:[{rule_id:'31',status,results:[],counts:{},coverage:{incomplete_scopes:[]},basis_catalog:[],
      package_sha256:'package-v1',program_version:'program-v1',execution_error:{error_type:'ProgramError',reason:safeReason,program_version:'program-v1'}}]};
}
const map = value => toCompilerResult(value,['sjtu_rule_31']);

describe('compiler execution failure presentation', () => {
  it('shows the bounded host reason for empty-result ERROR without claiming compliance', () => {
    const input=report();const original=structuredClone(input);const result=map(input);const run=result.rule_runs[0];
    expect(run.execution_status).toBe('error');expect(run.outcome).toBe('inconclusive');expect(run.findings).toEqual([]);
    expect(result.summary.error_rule_count).toBe(1);expect(result.summary.completed_rule_count).toBe(0);
    expect(run.message).toContain(safeReason);expect(run.message).toContain('当前版本');
    expect(run.compiler_runtime_status).toBe('candidate_rejected');expect(run.compiler_counts).toEqual({});
    expect(run.package_sha256).toBe('package-v1');expect(run.runtime_version).toBe('report-release');
    expect(run.pipeline_version).toBe('pipeline-v1');expect(run.runtime_snapshot.active_version).toBe('current-release');
    expect(input).toEqual(original);
  });

  it('explains the failed baseline and retained version while keeping a healthy selected rule passed', () => {
    const input=report('PASS');delete input.rules[0].execution_error;
    input.runtime.status='execution_error_unrecoverable';
    input.runtime.unrecoverable_baseline_failures=[{rule_id:'32',error_type:'ProgramError',reason:'Known baseline worker rejection'},
      {rule_id:'33',error_type:'ModelError',reason:'PRIVATE NETWORK CONFIG'}];
    input.runtime.reason='PRIVATE RUNTIME TRACE';
    const result=map(input);const run=result.rule_runs[0];
    expect(run.execution_status).toBe('completed');expect(run.outcome).toBe('passed');expect(result.summary.error_rule_count).toBe(0);
    expect(run.compiler_runtime_status).toBe('execution_error_unrecoverable');
    expect(run.message).toContain('基线');expect(run.message).toContain('停止');expect(run.message).toContain('当前版本');
    expect(run.message).toContain('Known baseline worker rejection');expect(run.message).not.toContain('PRIVATE');
  });

  it.each([null,17,{message:'PRIVATE OBJECT'},'x'.repeat(1001)])('does not stringify or expose an invalid host reason (%j)', reason => {
    const input=report();input.rules[0].execution_error.reason=reason;input.runtime.status='execution_error_unrecoverable';
    input.runtime.unrecoverable_baseline_failures=[{error_type:'ProgramError',reason}];
    const run=map(input).rule_runs[0];
    expect(run.execution_status).toBe('error');expect(run.outcome).toBe('inconclusive');
    expect(run.message).toContain('基线');expect(run.message).toContain('当前版本');
    expect(run.message).not.toContain('PRIVATE');expect(run.message).not.toContain('[object Object]');
    expect(run.message).not.toContain('x'.repeat(1001));
  });

  it('does not display unclassified exception text or unstructured runtime fields', () => {
    const input=report();input.rules[0].execution_error={error_type:'ModelError',reason:'PRIVATE MODEL CONFIG'};
    input.runtime.status='execution_error_unrecoverable';input.runtime.reason='PRIVATE RUNTIME TRACE';
    input.runtime.unrecoverable_baseline_failures=[{error_type:'OSError',reason:'PRIVATE HOST PATH'}];
    const run=map(input).rule_runs[0];expect(run.message).toContain('基线');expect(run.message).not.toContain('PRIVATE');
  });

  it.each([
    ['PASS','completed','passed'],['VIOLATION','completed','issues_found'],['UNKNOWN','completed','inconclusive'],
    ['ERROR','error','inconclusive'],['NOT_APPLICABLE','completed','not_applicable'],
  ])('preserves the %s terminal mapping when refinement stops', (status,execution,outcome) => {
    const input=report(status);input.runtime.status='execution_error_unrecoverable';
    if(status!=='ERROR')delete input.rules[0].execution_error;
    if(status==='VIOLATION')input.rules[0].results=[{node_id:'n',status:'VIOLATION',message:'Existing defect',basis:[],reasons:[]}];
    const run=map(input).rule_runs[0];
    expect(run.execution_status).toBe(execution);expect(run.outcome).toBe(outcome);
    expect(run.compiler_runtime_status).toBe('execution_error_unrecoverable');
    expect(run.package_sha256).toBe('package-v1');expect(run.runtime_version).toBe('report-release');
    expect(run.compiler_counts).toEqual({});expect(run.coverage).toEqual({incomplete_scopes:[]});
    expect(run.message).toContain('当前版本');
  });

  it('bounds displayed baseline reasons without adding findings or changing terminal status', () => {
    const input=report('PASS');delete input.rules[0].execution_error;input.runtime.status='execution_error_unrecoverable';
    input.runtime.unrecoverable_baseline_failures=Array.from({length:4},(unused,index)=>({error_type:'ProgramError',reason:`baseline-${index}`}));
    const run=map(input).rule_runs[0];expect(run.message).toContain('baseline-0');expect(run.message).toContain('baseline-2');
    expect(run.message).not.toContain('baseline-3');expect(run.findings).toEqual([]);expect(run.outcome).toBe('passed');
  });
});
