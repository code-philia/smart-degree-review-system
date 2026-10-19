import { describe,it,expect } from 'vitest';
import { createRequire } from 'node:module';
const require=createRequire(import.meta.url);
const {toCompilerResult}=require('../src/normative/paperCompilerService');
function raw(status='UNKNOWN',findings=[]) {
 return {schema_version:'paper-check/1.0',publication:{public:{status:findings.length?'ALERT':'NO_ALERT',findings},artifact:'/PRIVATE/gate.json'},
 rules:[{rule_id:'31',status,counts:{UNKNOWN:7},coverage:{incomplete_scopes:['PRIVATE_SCOPE']},basis_catalog:[{id:'b',text:'Normative basis'}],
 results:[{node_id:'n',check_id:'a',status:'VIOLATION',message:'UNCONFIRMED CHECK A',location_mode:'source',location:{page_number:1}},
 {node_id:'n',check_id:'b',status:'VIOLATION',message:'UNCONFIRMED CHECK B'}]}]};
}
describe('confirmed-only compiler publication',()=>{
 it('NO_ALERT is neither pass nor unknown presentation and does not publish proposed findings',()=>{
  const value=toCompilerResult(raw(),['sjtu_rule_31']);const run=value.rule_runs[0];
  expect(run.publication_status).toBe('NO_ALERT');expect(run.outcome).toBe('inconclusive');
  expect(run.message).toBe('未触发告警');expect(run.findings).toEqual([]);expect(run.compiler_diagnostics).toEqual([]);
  expect(run.compiler_counts).toBeUndefined();expect(run.coverage).toBeUndefined();
  expect(JSON.stringify(value)).not.toMatch(/UNKNOWN|PRIVATE|UNCONFIRMED|无法判定/);
 });
 it('publishes one independently confirmed node, not every original check on that node',()=>{
  const finding={rule_id:'31',node_id:'n',status:'VIOLATION',message:'Confirmed obligation',
   evidence:[[{kind:'normative_span',basis_id:'b',quote:'Normative basis'}],[{kind:'source_span',quote:'Paper source'}]]};
  const run=toCompilerResult(raw('VIOLATION',[finding]),['sjtu_rule_31']).rule_runs[0];
  expect(run.publication_status).toBe('ALERT');expect(run.outcome).toBe('issues_found');
  expect(run.findings).toHaveLength(1);expect(run.findings[0].message).toBe('Confirmed obligation');
  expect(run.findings[0].location).toEqual({page_number:1});expect(run.findings[0].basis_details[0].id).toBe('b');
  expect(run.findings[0].evidence.some(e=>e.quote==='Paper source')).toBe(true);
 });
 it('keeps ERROR as execution failure even when publication has no alert',()=>{
  const value=raw('ERROR');value.rules[0].results=[];value.rules[0].execution_error={error_type:'ProgramError',reason:'division by zero'};
  const result=toCompilerResult(value,['sjtu_rule_31']);const run=result.rule_runs[0];
  expect(run.execution_status).toBe('error');expect(run.outcome).toBe('inconclusive');expect(result.summary.error_rule_count).toBe(1);
  expect(run.message).toContain('执行失败');expect(run.message).not.toBe('未触发告警');expect(run.findings).toEqual([]);
 });
});
