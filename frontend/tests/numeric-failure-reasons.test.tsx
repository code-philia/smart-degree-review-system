import {afterEach, expect, it} from 'vitest';
import {cleanup, render, screen} from '@testing-library/react';
import {numericExecutionWarnings} from '../src/components/paperLint/model';
import {FindingsPane} from '../src/components/paperLint/FindingsPane';
import {setLocale} from '../src/i18n/locale';
import {buildExportReport} from '../src/utils/reportExport/model';
import {localizeExportReport} from '../src/utils/reportExport/presentation';
import {fixture} from './fixtures/reportExport';

const rule = 'abstract_numeric_consistency_check';
const run = (failure: unknown, extra = {}) => ({rule_id:rule, rule_run_id:'unit-error',
  severity:'warning', execution_status:'error', outcome:'inconclusive', findings:[],
  message:'语义检测执行失败', params:{failure,...extra}} as any);
afterEach(()=>{cleanup();setLocale('zh');});

it.each([
  [{error_type:'ContractError',stage:'structure_locator',message:'numeric value is not a candidate in declaration source'}, /数值及单位/],
  [{error_type:'RuntimeError',message:'校内 DeepSeek 请求失败（HTTP 429）：rate limit'}, /请求受限/],
  [{error_type:'TimeoutError',message:'timed out'}, /连接超时/],
  [{error_type:'RuntimeError',message:'HTTP Error 503: Service Unavailable'}, /暂不可用/],
  [{error_type:'RuntimeError',message:'校内 DeepSeek 请求失败（HTTP 500）：Internal Server Error'}, /暂不可用/],
  [{error_type:'ValueError',message:'DeepSeek returned invalid JSON'}, /返回结果未通过校验/],
  [{error_type:'RuntimeError',message:'unrecognized processing failure'}, /系统处理异常/],
])('reports the actual failure category and administrator email', (failure, reason) => {
  const source=run(failure), before=JSON.stringify(source);
  const warning=numericExecutionWarnings(source)[0];
  expect(warning.reason).toMatch(reason);
  expect(warning.reason).not.toMatch(/人数较多|API 调用暂时繁忙/);
  expect(warning.suggestion).toContain('j82279240@gmail.com');
  expect(JSON.stringify(source)).toBe(before);
});

it('does not advertise retries for source validation bugs or infer throttling from a provider name',()=>{
  const warning=numericExecutionWarnings(run({error_type:'ContractError',message:'DeepSeek numeric source mismatch'}))[0];
  expect(warning.reason).not.toMatch(/繁忙|受限/);
  expect(warning.suggestion).not.toMatch(/稍后重试/);
});

it('handles per-declaration validation errors without changing valid findings',()=>{
  const source=run(undefined,{validation_errors:[{declaration_id:'d2',type:'TimeoutError',message:'timed out'}],
    numeric_results:[{declaration_id:'d1',status:'consistent',evidence:[]}]});
  const before=JSON.stringify(source);
  expect(numericExecutionWarnings(source)[0].reason).toMatch(/连接超时/);
  expect(JSON.stringify(source)).toBe(before);
});

it('recognizes evidence-validation diagnostics without an exception type',()=>{
  const source=run(undefined,{validation_errors:[{declaration_id:'d2',errors:['untraceable_quote']}]});
  expect(numericExecutionWarnings(source)[0].reason).toMatch(/返回结果未通过校验/);
});

it('recognizes unknown declaration diagnostics as a model validation failure',()=>{
  const source=run(undefined,{validation_errors:[{kind:'unknown_declaration',ids:['bogus']}]});
  expect(numericExecutionWarnings(source)[0].reason).toMatch(/返回结果未通过校验/);
});

it.each(['zh','en'] as const)('renders the unit parsing error and exports the same reason in %s',locale=>{
  setLocale(locale);
  const source=run({error_type:'ContractError',stage:'structure_locator',message:'numeric value is not a candidate in declaration source'});
  render(<FindingsPane findings={[]} rules={[{rule_id:rule,title:'论点论据一致性检测'}] as any}
    ruleRuns={[source]} selectedRuleIds={[rule]} activeFindingKey={null} activeAnchorId={null}
    onFindingClick={()=>{}} onAnchorClick={()=>{}} executionWarnings={numericExecutionWarnings(source)}/>);
  expect(screen.getByText(locale==='zh'?/系统解析部分数值及单位时出错/:/could not correctly parse some numerical values and units/)).toBeInTheDocument();
  expect(screen.getByText(/j82279240@gmail.com/)).toBeInTheDocument();
  const report=structuredClone(fixture);report.result.rule_runs=[source];report.selected_rule_ids=[rule];
  const exported=localizeExportReport(buildExportReport(report,[{rule_id:rule,title:'论点论据一致性检测'}] as any),locale);
  expect(exported.findings[0].message).toMatch(locale==='zh'?/数值及单位/:/numerical values and units/);
  expect(exported.findings[0].suggestions.join(' ')).toContain('j82279240@gmail.com');
});
