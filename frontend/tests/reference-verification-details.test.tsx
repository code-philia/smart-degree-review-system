import { act, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { setLocale } from '../src/i18n/locale';
import {
  ReferenceVerificationDetails,
  ReferenceVerificationOverview,
} from '../src/components/paperLint/ReferenceVerificationDetails';
import { FindingsPane } from '../src/components/paperLint/FindingsPane';
import type { PaperLintRule, PaperLintRuleRun, ReferenceVerificationEntry } from '../src/api/paperLint';

const id = 'reference_verification_check';
const row = (category = 'mismatch'): ReferenceVerificationEntry => ({
  category,
  reason_code: 'metadata_conflict',
  entry: {
    id: 'ref-1',
    text: '[1] 原始题名. 王明. 2022.',
    title: '原始题名',
    authors: ['王明'],
    year: 2022,
    doi: '10.1000/example',
    location: { type: 'pdf_page', page_number: 12 },
  },
  matched: {
    title: 'Database title',
    authors: ['Wang Ming'],
    year: 2023,
    doi: '10.1000/example',
    url: 'https://doi.org/10.1000/example',
  },
  comparisons: [
    { field: 'title', cited: '原始题名', matched: 'Database title', status: 'different' },
    { field: 'year', cited: 2022, matched: 2023, status: 'different' },
  ],
  sources: [{ provider: 'crossref', url: 'https://api.crossref.org/works/10.1000%2Fexample', status: 'success' }],
  coverage: { complete: true, providers_succeeded: ['crossref'], providers_unavailable: [] },
});
afterEach(() => act(() => setLocale('zh')));

it.each([
  ['verified', '已核验', 'Verified'],
  ['suspected', '疑似伪造', 'Suspected fabrication'],
  ['mismatch', '信息不符', 'Metadata mismatch'],
  ['upgrade', '可升级', 'Published version available'],
  ['incomplete', '可补全', 'Can be completed'],
  ['unverified', '未核验', 'Unverified'],
])('labels %s in both languages while preserving original reference text', (category, zh, en) => {
  setLocale('zh');
  render(<ReferenceVerificationDetails check={row(category)} />);
  expect(screen.getByText(zh, { exact: true })).toBeInTheDocument();
  act(() => setLocale('en'));
  expect(screen.getByText(en, { exact: true })).toBeInTheDocument();
  expect(screen.getByText('[1] 原始题名. 王明. 2022.', { exact: true })).toBeInTheDocument();
});

it('shows field comparisons and escaped original metadata with keyboard-accessible disclosure', async () => {
  setLocale('en');
  const user = userEvent.setup();
  const entry = row();
  entry.entry.text = '<img src=x onerror=alert(1)> 语言';
  render(<ReferenceVerificationDetails check={entry} />);
  expect(screen.getByText('<img src=x onerror=alert(1)> 语言', { exact: true })).toBeInTheDocument();
  expect(screen.queryByRole('img')).not.toBeInTheDocument();
  const summary = screen.getByText('Compare fields (2)', { exact: true });
  expect(summary.closest('details')).toHaveAttribute('open');
  summary.focus();
  expect(summary).toHaveFocus();
  // user-event does not synthesize native Enter activation for <summary>.
  await user.click(summary);
  expect(summary.closest('details')).not.toHaveAttribute('open');
  await user.click(summary);
  expect(summary.closest('details')).toHaveAttribute('open');
  expect(screen.getByText('Original citation', { exact: true })).toBeVisible();
  expect(screen.getByText('Database record', { exact: true })).toBeVisible();
  expect(screen.getByText('原始题名', { exact: true })).toBeVisible();
  expect(screen.getByText('Database title', { exact: true })).toBeVisible();
  expect(screen.getByText('2022', { exact: true })).toBeVisible();
  expect(screen.getByText('2023', { exact: true })).toBeVisible();
});

it('flows PDF citation line breaks into one readable paragraph without changing the stored evidence', () => {
  setLocale('en');
  const check = row('verified');
  const doi = `https://doi.org/10.1234/${'long-doi-segment-'.repeat(12)}`;
  const original = `[19]\nSmith J, Wang M.\nA complete publication title. 2023.\n${doi}`;
  check.entry.text = original;
  const { container } = render(<ReferenceVerificationDetails check={check} />);
  const paragraph = container.querySelector('.reference-verification-original h4');
  expect(paragraph?.textContent).toBe(`[19] Smith J, Wang M. A complete publication title. 2023. ${doi}`);
  expect(check.entry.text).toBe(original);
});

it('opens the authoritative DOI without showing technical provider links', () => {
  const check = row('verified');
  check.entry.doi = null;
  check.matched!.doi = '10.5281/zenodo.12345';
  check.sources = [{ provider: 'datacite', url: 'https://api.datacite.org/dois/10.5281/zenodo.12345', status: 'success' }];
  render(<ReferenceVerificationDetails check={check} />);
  expect(screen.getByRole('link', { name: '打开 DOI' })).toHaveAttribute('href', 'https://doi.org/10.5281/zenodo.12345');
  expect(screen.queryByRole('link', { name: 'DataCite' })).not.toBeInTheDocument();
});

it.each(['zh', 'en'])('keeps unavailable reasons while omitting the requested technical sources section (%s)', (locale) => {
  setLocale(locale);
  const entry = row('unverified');
  entry.reason_code = 'provider_unavailable';
  entry.coverage = { complete: false, providers_unavailable: ['openalex'] };
  entry.sources = [
    { provider: 'crossref', url: 'https://api.crossref.org/works?query.bibliographic=title', status: 'success' },
    { provider: 'openalex', url: 'https://api.openalex.org/works?search=title', status: 'timeout' },
    ...[
      'javascript:alert(1)',
      'https://api.crossref.org.evil.test/works',
      'https://user:pass@doi.org/10.1000/example',
      'https://api.openalex.org/works?api_key=secret',
      'data:text/html,evil',
    ].map((url) => ({ provider: 'invalid', url, status: 'success' })),
  ];
  render(<ReferenceVerificationDetails check={entry} />);
  const links = screen.getAllByRole('link');
  expect(links).toHaveLength(3);
  for (const link of links) {
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  }
  expect(screen.queryByText(locale === 'en' ? 'Some sources were unavailable; verification coverage is incomplete.' : '部分数据源不可用，核验覆盖不完整。')).not.toBeInTheDocument();
  expect(screen.getByText(locale === 'en' ? 'Source temporarily unavailable' : '数据源暂不可用', { exact: true })).toBeInTheDocument();
  expect(screen.queryByText(locale === 'en' ? 'Verification sources' : '核验来源', { exact: true })).not.toBeInTheDocument();
  expect(screen.getByText(locale === 'en' ? /does not establish a citation error/ : /未核验不表示引用存在问题/)).toBeInTheDocument();
});

const callbacks = { onFindingClick: vi.fn(), onAnchorClick: vi.fn(), activeFindingKey: null, activeAnchorId: null };
const rules = [{ rule_id: id, title: '参考文献真实性核验' }] as PaperLintRule[];
function run(entries: ReferenceVerificationEntry[]): PaperLintRuleRun {
  return {
    rule_id: id,
    rule_run_id: 'refs',
    severity: 'info',
    execution_status: 'completed',
    outcome: 'passed',
    findings: [],
    params: {
      reference_verification: {
        counts: { verified: entries.length },
        entries,
        native_only: true,
        coverage_complete: true,
      },
    },
  };
}

it.each(['zh', 'en'])(
  'shows verified-only references and actual counts after selecting the new rule (%s)',
  async (locale) => {
    setLocale(locale);
    const user = userEvent.setup();
    const verified = { ...row('verified'), reason_code: 'identifier_verified' };
    render(
      <FindingsPane {...callbacks} rules={rules} selectedRuleIds={[id]} ruleRuns={[run([verified])]} findings={[]} />,
    );
    fireEvent.keyDown(screen.getByRole('combobox'), { key: 'ArrowDown' });
    const option = within(await screen.findByRole('listbox')).getAllByRole('option')[1];
    act(() => {
      option.focus();
      fireEvent.keyDown(option, { key: 'Enter' });
    });
    const overview = screen.getByRole('region', {
      name: locale === 'en' ? 'Reference verification summary' : '参考文献核验概览',
    });
    expect(overview).toHaveTextContent(locale === 'en' ? '1 reference processed' : '已处理 1 条');
    expect(
      screen.queryByText(locale === 'en' ? 'No issues found for this check' : '本规则未检测出问题'),
    ).not.toBeInTheDocument();
    await user.click(
      within(overview).getByText(locale === 'en' ? 'Verified references (1)' : '已核验条目（1）', { exact: true }),
    );
    expect(within(overview).getByText('[1] 原始题名. 王明. 2022.', { exact: true })).toBeVisible();
  },
);

it('preserves PDF selection and feedback while excluding model repair for new reference results', async () => {
  setLocale('zh');
  callbacks.onFindingClick.mockClear();
  const user = userEvent.setup();
  const check = row();
  const finding = {
    finding_id: 'ref-1',
    rule_id: id,
    message: '信息不符',
    message_en: 'Metadata mismatch',
    suggestion: '人工核对',
    reference_check: check,
    location: check.entry.location,
  };
  const ruleRun = { ...run([check]), outcome: 'issues_found' as const, findings: [finding] };
  render(
    <FindingsPane
      {...callbacks}
      rules={rules}
      selectedRuleIds={[id]}
      ruleRuns={[ruleRun]}
      findings={[{ key: 'ref-key', finding, ruleRun, index: 0 }]}
      onGenerateRepairSuggestion={vi.fn()}
      onFindingFeedback={vi.fn()}
    />,
  );
  expect(screen.getByText('信息不符', { exact: true })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: '获取修复建议' })).not.toBeInTheDocument();
  expect(screen.getByText('这个问题的判断是否准确？')).toBeInTheDocument();
  await user.click(screen.getByText('字段比较（2）', { exact: true }));
  expect(callbacks.onFindingClick).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button', { name: /跳到/ }));
  expect(callbacks.onFindingClick).toHaveBeenCalledWith('ref-key');
});

it('reports zero processed references for an extraction failure placeholder', () => {
  setLocale('en');
  render(
    <ReferenceVerificationOverview
      summary={{
        entries: [
          { category: 'unverified', reason_code: 'bibliography_not_extracted', entry: { id: 'unreadable', text: '' } },
        ],
        native_only: true,
        coverage_complete: false,
      }}
    />,
  );
  expect(screen.getByText('0 references processed', { exact: true })).toBeInTheDocument();
  expect(screen.queryByText('1 reference processed', { exact: true })).not.toBeInTheDocument();
  expect(screen.queryByText(/Some entries or sources have incomplete coverage/)).not.toBeInTheDocument();
  expect(screen.getByText('Unverified', { exact: true })).toBeInTheDocument();
});
