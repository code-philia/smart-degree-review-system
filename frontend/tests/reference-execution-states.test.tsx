import { fireEvent, render, screen, within } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import type { PaperLintRuleRun } from '../src/api/paperLint';
import { FindingsPane } from '../src/components/paperLint/FindingsPane';
import { flattenPaperLintFindings, genericExecutionWarnings, paperLintPresentation } from '../src/components/paperLint/model';
import { buildExportReport } from '../src/utils/reportExport/model';
import { fixture } from './fixtures/reportExport';

const id = 'sjtu_rule_32';
const rules = [{ rule_id: id, title: '引用的外部文献不存在' }];
const props = { rules, selectedRuleIds: [id], activeFindingKey: null, activeAnchorId: null,
  onFindingClick: vi.fn(), onAnchorClick: vi.fn() };
const run: PaperLintRuleRun = { rule_id: id, rule_run_id: 'references', severity: 'info',
  execution_status: 'completed', outcome: 'inconclusive', message: '检索资源暂不可用：额度已用尽。',
  params: { reference_verification: { total: 3, verified: 0, unresolved: 2, unavailable: 1 } },
  findings: [
    { finding_id: 'suspect', rule_id: id, message: '有检索证据的疑点', prompt_only: true, reference_review: 'supported_suspicion' },
    { finding_id: 'reference-info-blocked-existence-0', rule_id: id, message: '旧版生成的额度不足提示', prompt_only: true, reference_review: 'insufficient_evidence' },
  ],
  compiler_diagnostics: [
    { node_id: 'blocked', check_id: 'existence', status: 'UNKNOWN', reasons: ['reference_lookup_unavailable: SERPAPI_QUOTA_EXHAUSTED'], evidence: [] },
    { node_id: 'searched', check_id: 'existence', status: 'UNKNOWN', reasons: ['reference_not_matched'], evidence: [] },
  ],
};

it.each([false, true])('keeps searched results blue and resource-blocked entries only in purple without a review badge (live=%s)', async running => {
  const result = paperLintPresentation({ ...fixture.result, rule_runs: [run] });
  expect(result.summary).toMatchObject({ info_finding_count: 2, execution_warning_count: 1, finding_count: 3 });
  expect(result.rule_runs[0].findings.map(f => f.finding_id)).not.toContain('reference-info-blocked-existence-0');
  expect(paperLintPresentation(result)).toEqual(result);
  expect(buildExportReport({ ...fixture, result }, rules, null).summary).toMatchObject({ info_finding_count: 2, execution_warning_count: 1 });
  render(<FindingsPane {...props} running={running} ruleRuns={[run]} findings={flattenPaperLintFindings(result)} executionWarnings={genericExecutionWarnings([run])} />);
  for (const category of ['全部', '提示 2', '规则未实现警告 1']) {
    fireEvent.click(screen.getByRole('button', { name: category, exact: true }));
    const trigger = screen.getByRole('combobox');
    expect(trigger).not.toHaveTextContent('待核查');
    fireEvent.keyDown(trigger, { key: 'ArrowDown' });
    const list = await screen.findByRole('listbox');
    const option = within(list).getByRole('option', { name: /^引用的外部文献不存在，/ });
    expect(option).not.toHaveTextContent('待核查');
    fireEvent.keyDown(list, { key: 'Escape' });
  }
});

it('moves all quota-blocked diagnostics out of Info even in old reports without resource flags', () => {
  const blocked = { ...run, params: undefined, message: '部分引用未完成核验。', findings: run.findings.slice(1), compiler_diagnostics: run.compiler_diagnostics!.slice(0, 1) };
  const result = paperLintPresentation({ ...fixture.result, rule_runs: [blocked] });
  expect(result.summary).toMatchObject({ info_finding_count: 0, execution_warning_count: 1, finding_count: 1 });
  expect(genericExecutionWarnings([blocked])).toHaveLength(1);
  expect(result.rule_runs[0].findings).toEqual([]);
});

it('replaces a legacy success sentinel with a resource explanation in purple warnings and exports', () => {
  const legacy = { ...run, params: undefined, message: '未触发告警', findings: run.findings.slice(1), compiler_diagnostics: run.compiler_diagnostics!.slice(0, 1) };
  const result = paperLintPresentation({ ...fixture.result, rule_runs: [legacy] });
  expect(result.rule_runs[0].message).toContain('额度');
  expect(genericExecutionWarnings([legacy])[0].reason).toContain('额度');
  expect(buildExportReport({ ...fixture, result }, rules, null).rules[0].message).toContain('额度');
});
