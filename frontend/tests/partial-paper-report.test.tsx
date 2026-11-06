import { render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { LivePaperLintReport } from '../src/components/paperLint/LivePaperLintReport';
import { compilerPublicationLabel, paperLintPresentation } from '../src/components/paperLint/model';
import { buildExportReport } from '../src/utils/reportExport/model';
import { fixture } from './fixtures/reportExport';
import type { PaperLintRuleRun } from '../src/api/paperLint';

vi.mock('../src/components/paperLint/PdfPane', () => ({ PdfPane: () => <div /> }));
const id = 'sjtu_rule_32';
const unavailable: PaperLintRuleRun = { rule_id: id, rule_run_id: 'missing-references', severity: 'info',
  execution_status: 'unsupported', evidence_mode: 'unsupported', outcome: 'inconclusive', findings: [],
  message: '未检测：缺少参考文献部分，该规则依赖参考文献内容。' };

it.each([
  unavailable,
  { ...unavailable, execution_status: 'completed' as const, evidence_mode: 'native' as const,
    message: '检索资源暂不可用：请稍后重试。这不表示引用存在问题。' },
])('keeps unavailable runs distinct from passes in live, saved and exported reports ($execution_status)', run => {
  render(<LivePaperLintReport file={{ name: 'paper.pdf', url: '/paper.pdf' }} rules={[]}
    runs={[run]} selectedRuleIds={[id]} />);
  expect(screen.getByText('错误总数').closest('div')).toHaveTextContent('1');
  expect(screen.getAllByText(run.message! as string).length).toBeGreaterThan(0);
  expect(screen.queryByText('未检测出问题')).not.toBeInTheDocument();
  expect(screen.queryByText('未发现疑似不存在的引用')).not.toBeInTheDocument();
  const report = { ...fixture, result: { ...fixture.result, rule_runs: [run] } };
  const presented = paperLintPresentation(report.result);
  expect(paperLintPresentation(presented)).toEqual(presented);
  expect(presented.summary).toMatchObject({ finding_count: 1, execution_warning_count: 1 });
  const exported = buildExportReport(report, [], null);
  expect(exported.summary.finding_count).toBe(1);
  expect(exported.rules[0].message).toBe(run.message);
  expect(exported.rules[0].status).toBe('未能检测');
  expect(compilerPublicationLabel(presented.rule_runs[0])).not.toBe('未触发告警');
});

it('retains the resource warning when a reference run also has valid findings', () => {
  const run = { ...unavailable, execution_status: 'completed' as const, outcome: 'issues_found' as const,
    params: { reference_resources_unavailable: true, reference_verification: { unavailable: 1 } },
    message: '发现 1 条疑似不存在的引用。检索资源暂不可用：另有 1 条未完成核验。',
    findings: [{ finding_id: 'confirmed-ref', rule_id: id, message: '已有证据的引用疑点' }] };
  const result = paperLintPresentation({ ...fixture.result, rule_runs: [run] });
  expect(result.summary).toMatchObject({ finding_count: 2, execution_warning_count: 1, info_finding_count: 1 });
  expect(result.rule_runs[0].message).toContain('检索资源暂不可用');
  expect(paperLintPresentation(result)).toEqual(result);
  render(<LivePaperLintReport file={{ name: 'paper.pdf', url: '/paper.pdf' }} rules={[]}
    runs={[run]} selectedRuleIds={[id]} />);
  expect(screen.getByText('错误总数').closest('div')).toHaveTextContent('2');
  expect(screen.getAllByText(/检索资源暂不可用/).length).toBeGreaterThan(0);
});
