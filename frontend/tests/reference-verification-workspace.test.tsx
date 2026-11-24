import { act, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { PaperLintWorkspace } from '../src/components/paperLint/Workspace';
import { flattenPaperLintFindings } from '../src/components/paperLint/model';
import { buildAnnotations } from '../src/components/paperLint/geometry';
import type { PaperLintFindingItem } from '../src/components/paperLint/model';
import type { PaperLintRule, PaperLintRuleRun, ReferenceVerificationEntry } from '../src/api/paperLint';
import { setLocale } from '../src/i18n/locale';

const preview = vi.hoisted(() => ({ current: null as null | {
  findings: PaperLintFindingItem[]; activeFindingKey: string | null; navigationRequest: number;
} }));
// PDF loading/rendering needs a browser worker. Keep the workspace and report
// pane real and observe the navigation contract at the PDF component boundary.
vi.mock('../src/components/paperLint/PdfPane', () => ({ PdfPane: (props: NonNullable<typeof preview.current>) => {
  preview.current = props;
  return null;
} }));

const ruleId = 'reference_verification_check';
const rules = [{ rule_id: ruleId, title: '引用文献是否不存在' }] as PaperLintRule[];

function storedReport() {
  const verified = [0, 3, 8, 14, 21];
  const entries: ReferenceVerificationEntry[] = Array.from({ length: 22 }, (_, index) => ({
    category: verified.includes(index) ? 'verified' : 'unverified',
    reason_code: verified.includes(index) ? 'metadata_verified' : 'provider_unavailable',
    entry: { id: `ref-${index + 1}`, text: `[${index + 1}] Original reference ${index + 1}`, title: `Original reference ${index + 1}`,
      location: { type: 'pdf_page', page_number: index + 10 } },
    comparisons: [],
    sources: [{ provider: 'openalex', status: verified.includes(index) ? 'success' : 'timeout' }],
    coverage: { complete: verified.includes(index), providers_unavailable: verified.includes(index) ? [] : ['openalex'] },
  }));
  const run: PaperLintRuleRun = {
    rule_id: ruleId, rule_run_id: 'old-stored-reference-run', severity: 'info', execution_status: 'completed', outcome: 'inconclusive',
    findings: entries.filter(check => check.category !== 'verified').map(check => ({ finding_id: `finding-${check.entry.id}`, rule_id: ruleId,
      message: '未核验', location: check.entry.location, reference_check: check })),
    params: { reference_verification: { entries, counts: { verified: 5, unverified: 17 }, coverage_complete: false, native_only: true } },
  };
  return run;
}

afterEach(() => { preview.current = null; act(() => setLocale('zh')); });

async function selectReferenceRule() {
  fireEvent.keyDown(screen.getByRole('combobox'), { key: 'ArrowDown' });
  const option = within(await screen.findByRole('listbox')).getAllByRole('option')[1];
  act(() => { option.focus(); fireEvent.keyDown(option, { key: 'Enter' }); });
}

it.each(['zh', 'en'])('makes all 22 stored references navigable while keeping 17 findings (%s)', async locale => {
  setLocale(locale);
  const user = userEvent.setup();
  const run = storedReport();
  const stored = JSON.stringify(run);
  const findings = flattenPaperLintFindings({ rule_runs: [run] });
  render(<PaperLintWorkspace file={{ name: 'old-report.pdf', url: '/report.pdf' }} findings={findings}
    rules={rules} selectedRuleIds={[ruleId]} ruleRuns={[run]} />);
  await selectReferenceRule();
  const overview = screen.getByRole('region', { name: locale === 'en' ? 'Reference verification summary' : '参考文献核验概览' });
  expect(overview).toHaveTextContent(locale === 'en' ? '22 references processed' : '已处理 22 条');
  expect(screen.queryByText(locale === 'en' ? /Some entries or sources have incomplete coverage/ : '部分条目或数据源覆盖不足，请结合原文复核。')).not.toBeInTheDocument();
  await user.click(within(overview).getByText(locale === 'en' ? 'Verified references (5)' : '已核验条目（5）', { exact: true }));
  expect(findings).toHaveLength(17);
  expect(screen.getAllByText(locale === 'en' ? 'Source temporarily unavailable' : '数据源暂不可用', { exact: true })).toHaveLength(17);
  expect(screen.getAllByText(locale === 'en' ? 'Timed out' : '超时', { exact: true })).toHaveLength(17);
  expect(screen.getAllByText(/^\[\d+\] Original reference \d+$/, { exact: true })).toHaveLength(22);
  expect(preview.current?.findings).toHaveLength(22);
  const verified = [{ id: 1, page: 10 }, { id: 4, page: 13 }, { id: 9, page: 18 }, { id: 15, page: 24 }, { id: 22, page: 31 }];
  for (const [index, reference] of verified.entries()) {
    expect(within(overview).getByText(`[${reference.id}] Original reference ${reference.id}`, { exact: true })).toBeVisible();
    const jump = within(overview).getByRole('button', { name: locale === 'en' ? `Jump to PDF page ${reference.page}` : `跳到 PDF 第 ${reference.page} 页` });
    jump.focus();
    await user.keyboard(index % 2 ? ' ' : '{Enter}');
    const selected = preview.current?.findings.find(item => item.key === preview.current?.activeFindingKey);
    expect(selected?.finding.reference_check?.entry.id).toBe(`ref-${reference.id}`);
    expect(preview.current?.navigationRequest).toBe(index + 1);
  }
  expect(flattenPaperLintFindings({ rule_runs: [run] })).toHaveLength(17);
  expect(JSON.stringify(run)).toBe(stored);
});

it('keeps a verified entry visible without inventing a PDF position', async () => {
  setLocale('zh');
  const user = userEvent.setup();
  const run = storedReport();
  const summary = run.params!.reference_verification as { entries: ReferenceVerificationEntry[] };
  summary.entries[0].entry.location = null;
  render(<PaperLintWorkspace file={{ name: 'old-report.pdf', url: '/report.pdf' }} findings={flattenPaperLintFindings({ rule_runs: [run] })}
    rules={rules} selectedRuleIds={[ruleId]} ruleRuns={[run]} />);
  await selectReferenceRule();
  const overview = screen.getByRole('region', { name: '参考文献核验概览' });
  await user.click(within(overview).getByText('已核验条目（5）', { exact: true }));
  expect(within(overview).getByText('[1] Original reference 1', { exact: true })).toBeVisible();
  expect(within(overview).queryByRole('button', { name: '跳到 PDF 第 10 页' })).not.toBeInTheDocument();
  expect(within(overview).getAllByRole('button', { name: /跳到 PDF 第/ })).toHaveLength(4);
});

it('uses native boxes for verified PDF markers without labeling them as problems', () => {
  const run = storedReport();
  const summary = run.params!.reference_verification as { entries: ReferenceVerificationEntry[] };
  const verified = summary.entries.filter(check => check.category === 'verified');
  for (let index = 0; index < 5; index++) {
    const rect = { x1: 40, y1: 60 + index * 30, x2: 420, y2: 80 + index * 30, width: 600, height: 800, page_number: 10 };
    verified[index].entry.location = { type: 'pdf_bbox', page_number: 10, bounding_rect: rect, rects: [rect], text_excerpt: verified[index].entry.text };
  }
  render(<PaperLintWorkspace file={{ name: 'native.pdf', url: '/native.pdf' }} findings={flattenPaperLintFindings({ rule_runs: [run] })}
    rules={rules} selectedRuleIds={[ruleId]} ruleRuns={[run]} />);
  const annotations = buildAnnotations(preview.current!.findings);
  expect(annotations).toHaveLength(5);
  expect(annotations.map(annotation => annotation.boundingRect.y1)).toEqual([60, 90, 120, 150, 180]);
  expect(annotations.every(annotation => annotation.anchorLabel === '已核验 / Verified')).toBe(true);
  expect(flattenPaperLintFindings({ rule_runs: [run] })).toHaveLength(17);
});
