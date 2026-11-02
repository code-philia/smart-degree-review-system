import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useParams } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import NormativeCheckPage from '../src/pages/NormativeCheckPage';
import {
  fetchPaperLintJob,
  fetchPaperLintReport,
  fetchReviewPilotPaperLintRules,
  runReviewPilotPaperLint,
  type PaperLintRule,
} from '../src/api/paperLint';
import { fixture } from './fixtures/reportExport';

vi.mock('../src/auth/AuthSessionProvider', () => ({
  useAuthSession: () => ({ status: 'authenticated', user: { id: 'upload-student' } }),
}));
vi.mock('../src/api/paperLint', async () => ({
  ...(await vi.importActual('../src/api/paperLint')),
  fetchReviewPilotPaperLintRules: vi.fn(),
  runReviewPilotPaperLint: vi.fn(),
  fetchPaperLintJob: vi.fn(),
  fetchPaperLintReport: vi.fn(),
}));
vi.mock('../src/hooks/usePaperLintRepairSuggestions', () => ({
  usePaperLintRepairSuggestions: () => ({ repairSuggestionByFindingKey: {} }),
}));
vi.mock('../src/components/paperLint/PdfPane', () => ({
  PdfPane: ({ file, activeFindingKey }: { file: File | { name: string; url: string }; activeFindingKey: string | null }) =>
    <div aria-label="实时原文预览" data-source={'url' in file ? file.url : file.name} data-active={activeFindingKey} />,
}));

const rules: PaperLintRule[] = [
  ['sjtu_rule_18', '正文公式引用目标缺失', '核对公式编号'],
  ['typo_detection_check', '正文错别字检测', '核对文字表述'],
  ['bilingual_keywords_correspondence_check', '中英文关键词语义对应', '核对关键词语义'],
  ['unavailable-rule', '暂不可用规则', '服务暂未配置'],
].map(([rule_id, title, description], index) => ({
  rule_id,
  title,
  description,
  enabled_in_mvp: true,
  default_enabled: false,
  available: index < 3,
  default_severity: 'warning',
  execution_mode: 'deterministic',
  uses_external_model: false,
}));
const catalog = { engine: 'sjtu-local', mode: 'pdf_lint', semantic_model: 'deepseek-v4-flash', rules } as const;
const pendingJob = {
  job_id: 'upload-job',
  status: 'pending',
  report_id: null,
  error_message: null,
  created_at: '',
  updated_at: '',
} as const;
const pdf = () => new File(['%PDF-1.7'], '论文.pdf', { type: 'application/pdf' });
function ReportDestination() {
  return <h1>报告详情 {useParams().reportId}</h1>;
}
function showUpload() {
  return render(
    <MemoryRouter initialEntries={['/paper-upload']}>
      <Routes>
        <Route path="/paper-upload" element={<NormativeCheckPage mode="thirty" />} />
        <Route path="/reports/pdf/:reportId" element={<ReportDestination />} />
      </Routes>
    </MemoryRouter>,
  );
}
async function choosePdf() {
  await screen.findByText('已选择全部可用检测规则');
  fireEvent.change(screen.getByLabelText('上传待审查 PDF'), { target: { files: [pdf()] } });
}
beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  vi.mocked(fetchReviewPilotPaperLintRules).mockResolvedValue(catalog as never);
  vi.mocked(runReviewPilotPaperLint).mockResolvedValue(pendingJob);
  vi.mocked(fetchPaperLintJob).mockImplementation(() => new Promise(() => {}));
  vi.mocked(fetchPaperLintReport).mockResolvedValue(fixture);
});

it('starts with all available rules selected and collapsed below the two-line upload area', async () => {
  const user = userEvent.setup();
  showUpload();
  expect(screen.getByRole('heading', { name: '论文上传', exact: true })).toBeInTheDocument();
  expect(screen.getByText('点击或将文件拖拽至此处上传')).toBeInTheDocument();
  expect(screen.getByText('支持 pdf 格式（扫描版 pdf 除外），文件大小不超过 50MB；支持中英文检测')).toBeInTheDocument();
  expect(await screen.findByText('已选择全部可用检测规则')).toBeInTheDocument();
  expect(screen.queryByRole('checkbox', { name: /正文公式/ })).not.toBeInTheDocument();
  const expand = screen.getByRole('button', { name: '展开选择' });
  expect(expand).toHaveAttribute('aria-expanded', 'false');
  const input = screen.getByLabelText('上传待审查 PDF');
  expect(input.compareDocumentPosition(expand) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  await user.click(expand);
  for (const name of ['格式规范', '内容规范', '论文逻辑审查'])
    expect(screen.getByRole('heading', { name, exact: true })).toBeInTheDocument();
  expect(screen.getByRole('checkbox', { name: /正文公式引用目标缺失/ })).toBeChecked();
  expect(screen.getByRole('checkbox', { name: /正文错别字检测/ })).toBeChecked();
  expect(screen.getByRole('checkbox', { name: /中英文关键词语义对应/ })).toBeChecked();
  expect(screen.getByRole('checkbox', { name: /暂不可用规则/ })).toBeDisabled();
  expect(screen.getByRole('checkbox', { name: /暂不可用规则/ })).not.toBeChecked();
});

it('supports global and group selection, warns after clear, and retains the subset while collapsed', async () => {
  const user = userEvent.setup();
  showUpload();
  await choosePdf();
  await user.click(screen.getByRole('button', { name: '展开选择' }));
  await user.click(screen.getByRole('button', { name: '清空全部检测规则' }));
  expect(screen.getByText('请至少选择一项检测规则')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '开始检测', exact: true })).toBeDisabled();
  await user.click(screen.getByRole('checkbox', { name: /正文错别字检测/ }));
  expect(screen.queryByText('请至少选择一项检测规则')).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: '全选格式规范' }));
  expect(screen.getByRole('checkbox', { name: /正文公式/ })).toBeChecked();
  await user.click(screen.getByRole('button', { name: '清空格式规范' }));
  expect(screen.getByRole('checkbox', { name: /正文公式/ })).not.toBeChecked();
  await user.click(screen.getByRole('button', { name: '收起选择' }));
  expect(screen.getByText('已选择 1 项检测规则')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: '开始检测', exact: true }));
  expect(screen.getByRole('button', { name: '展开选择' })).toHaveAttribute('aria-expanded', 'false');
  await waitFor(() =>
    expect(runReviewPilotPaperLint).toHaveBeenCalledWith(
      expect.any(File),
      ['typo_detection_check'],
      false,
      expect.any(String),
      expect.any(Function),
    ),
  );
});

it('submits default rules without expanding and redirects completed jobs to the saved report', async () => {
  vi.mocked(fetchPaperLintJob).mockResolvedValue({ ...pendingJob, status: 'completed', report_id: fixture.id });
  showUpload();
  await choosePdf();
  fireEvent.click(screen.getByRole('button', { name: '开始检测', exact: true }));
  expect(await screen.findByRole('heading', { name: `报告详情 ${fixture.id}` })).toBeInTheDocument();
  expect(runReviewPilotPaperLint).toHaveBeenCalledWith(
    expect.any(File),
    rules.slice(0, 3).map((rule) => rule.rule_id),
    false,
    expect.any(String),
    expect.any(Function),
  );
  expect(fetchPaperLintReport).toHaveBeenCalledWith(fixture.id);
  expect(localStorage.getItem('paper-lint-active-job:upload-student')).toBeNull();
});

it('uses upload events and backend pending/running states for progress, with no invented completion or email promise', async () => {
  let finishUpload!: (value: typeof pendingJob) => void;
  let uploadProgress!: (value: number) => void;
  vi.mocked(runReviewPilotPaperLint).mockImplementation((_file, _ids, _consent, _request, onUpload) => {
    uploadProgress = onUpload!;
    return new Promise((resolve) => {
      finishUpload = resolve;
    });
  });
  vi.mocked(fetchPaperLintJob)
    .mockResolvedValueOnce(pendingJob)
    .mockImplementation(() => new Promise(() => {}));
  showUpload();
  await choosePdf();
  fireEvent.click(screen.getByRole('button', { name: '开始检测', exact: true }));
  await act(async () => uploadProgress(37));
  expect(screen.getByRole('progressbar', { name: '检测进度' })).toHaveAttribute('aria-valuetext', '正在上传，37%');
  await act(async () => finishUpload(pendingJob));
  expect(screen.getByRole('progressbar', { name: '检测进度' })).toHaveAttribute('aria-valuetext', '开始解析');
  expect(screen.queryByText(/通过邮件/)).not.toBeInTheDocument();
  expect(screen.queryByRole('heading', { name: /报告详情/ })).not.toBeInTheDocument();
});

it('restores a running subset and opens its saved report without another upload', async () => {
  let finishPoll!: (value: any) => void;
  localStorage.setItem(
    'paper-lint-active-job:upload-student',
    JSON.stringify({
      jobId: 'upload-job',
      requestId: 'old-request',
      filename: '之前的论文.pdf',
      selectedRuleIds: ['typo_detection_check'],
    }),
  );
  vi.mocked(fetchPaperLintJob).mockImplementation(
    () =>
      new Promise((resolve) => {
        finishPoll = resolve;
      }),
  );
  showUpload();
  expect(await screen.findByText('已选择 1 项检测规则')).toBeInTheDocument();
  await act(async () => finishPoll({ ...pendingJob, status: 'completed', report_id: fixture.id }));
  expect(await screen.findByRole('heading', { name: `报告详情 ${fixture.id}` })).toBeInTheDocument();
  expect(runReviewPilotPaperLint).not.toHaveBeenCalled();
});

it('updates real report progress while keeping report completion controlled by the server', async () => {
  let nextPoll!: (value: any) => void;
  vi.mocked(fetchPaperLintJob)
    .mockResolvedValueOnce({
      ...pendingJob,
      status: 'running',
      progress: {
        completed_rule_ids: ['sjtu_rule_18'],
        total_rule_ids: ['sjtu_rule_18', 'typo_detection_check', 'bilingual_keywords_correspondence_check'],
      },
    })
    .mockImplementation(() => new Promise(resolve => { nextPoll = resolve; }));
  showUpload();
  await choosePdf();
  fireEvent.click(screen.getByRole('button', { name: '开始检测', exact: true }));
  await waitFor(() =>
    expect(screen.getByRole('progressbar', { name: '检测进度' })).toHaveAttribute('aria-valuenow', '33'),
  );
  expect(screen.getByText('后台检测已开始，已完成 1 / 3 项规则。')).toBeInTheDocument();
  expect(screen.getByText('33%')).toBeInTheDocument();
  expect(screen.getAllByRole('progressbar', { name: '检测进度' })).toHaveLength(1);
  expect(screen.getByRole('progressbar', { name: '检测进度' }).querySelectorAll('svg circle')).toHaveLength(2);
  const progress = screen.getByRole('region', { name: '检测任务状态' });
  const liveReport = screen.getByRole('region', { name: '实时检测报告' });
  const instructions = screen.getByRole('complementary', { name: '检测说明' });
  expect(instructions.compareDocumentPosition(progress) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(progress.compareDocumentPosition(liveReport) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(within(liveReport).queryByRole('progressbar')).not.toBeInTheDocument();
  expect(screen.getByRole('region', { name: '论文上传与检测设置' })).toBeInTheDocument();
  expect(screen.getByText('正在检测，等待新的问题')).toBeInTheDocument();
  expect(screen.queryByText('未检测出问题')).not.toBeInTheDocument();
  await waitFor(() => expect(nextPoll).toBeTypeOf('function'));
  await act(async () => nextPoll({ ...pendingJob, status: 'running', progress: {
    completed_rule_ids: rules.slice(0, 3).map(rule => rule.rule_id),
    total_rule_ids: rules.slice(0, 3).map(rule => rule.rule_id),
  } }));
  expect(screen.getByRole('progressbar', { name: '检测进度' })).toHaveAttribute('aria-valuenow', '100');
  expect(screen.getByText(/正在保存报告/)).toBeInTheDocument();
  expect(screen.queryByRole('heading', { name: /报告详情/ })).not.toBeInTheDocument();
});

it('opens a synchronously saved report through the same detail route', async () => {
  vi.mocked(runReviewPilotPaperLint).mockResolvedValueOnce(fixture);
  showUpload();
  await choosePdf();
  fireEvent.click(screen.getByRole('button', { name: '开始检测', exact: true }));
  expect(await screen.findByRole('heading', { name: `报告详情 ${fixture.id}` })).toBeInTheDocument();
  expect(fetchPaperLintJob).not.toHaveBeenCalled();
});

it('leaves detection disabled when the catalog has no available rules', async () => {
  vi.mocked(fetchReviewPilotPaperLintRules).mockResolvedValue({
    ...catalog,
    rules: rules.map((rule) => ({ ...rule, available: false })),
  } as never);
  showUpload();
  expect(await screen.findByText('当前暂无可用检测规则，请稍后重试或联系管理员。')).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('上传待审查 PDF'), { target: { files: [pdf()] } });
  expect(screen.getByRole('button', { name: '开始检测', exact: true })).toBeDisabled();
  expect(runReviewPilotPaperLint).not.toHaveBeenCalled();
});

it('runs campus semantic rules without a separate processing checkbox', async () => {
  vi.mocked(fetchReviewPilotPaperLintRules).mockResolvedValue({
    ...catalog,
    rules: rules.map((rule) => ({ ...rule, uses_external_model: rule.rule_id === 'typo_detection_check' })),
  } as never);
  const user = userEvent.setup();
  showUpload();
  await choosePdf();
  expect(screen.getByRole('button', { name: '展开选择' })).toHaveAttribute('aria-expanded', 'false');
  expect(screen.queryByRole('checkbox', { name: /我确认本次论文相关文本允许/ })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: '开始检测', exact: true })).toBeEnabled();
  await user.click(screen.getByRole('button', { name: '开始检测', exact: true }));
  await waitFor(() =>
    expect(runReviewPilotPaperLint).toHaveBeenCalledWith(
      expect.any(File),
      expect.any(Array),
      true,
      expect.any(String),
      expect.any(Function),
    ),
  );
});

it('shows file validation and failed jobs without navigating or consuming another request automatically', async () => {
  showUpload();
  await screen.findByText('已选择全部可用检测规则');
  fireEvent.change(screen.getByLabelText('上传待审查 PDF'), {
    target: { files: [new File(['text'], 'wrong.txt', { type: 'text/plain' })] },
  });
  expect(screen.getByRole('alert')).toHaveTextContent('仅支持上传 PDF 文件');
  expect(runReviewPilotPaperLint).not.toHaveBeenCalled();
  vi.mocked(fetchPaperLintJob).mockResolvedValue({
    ...pendingJob,
    status: 'failed',
    error_message: '解析失败，请更换文件',
  });
  await choosePdf();
  fireEvent.click(screen.getByRole('button', { name: '开始检测', exact: true }));
  expect(await screen.findByRole('alert')).toHaveTextContent('解析失败，请更换文件');
  expect(screen.queryByRole('heading', { name: /报告详情/ })).not.toBeInTheDocument();
  expect(runReviewPilotPaperLint).toHaveBeenCalledTimes(1);
});

it('groups reference existence with content and selects the experimental rule by default', async () => {
  const extra = (rule_id: string, title: string) => ({ ...rules[0], rule_id, title });
  vi.mocked(fetchReviewPilotPaperLintRules).mockResolvedValue({ ...catalog, rules: [
    ...rules.slice(0, 3), extra('sjtu_rule_32', '引用的外部文献不存在'),
    extra('abstract_numeric_consistency_check', '摘要数值声明与实验结果一致性'),
  ] } as never);
  showUpload();
  fireEvent.click(await screen.findByRole('button', { name: '展开选择' }));
  const content = screen.getByRole('region', { name: '内容规范检测规则' });
  expect(within(content).getByRole('checkbox', { name: /外部文献/ })).toBeChecked();
  expect(within(content).getByRole('checkbox', { name: /错别字/ })).toBeChecked();
  expect(within(content).getByRole('checkbox', { name: /关键词语义/ })).toBeChecked();
  const experiment = screen.getByRole('region', { name: '论文逻辑审查检测规则' });
  expect(within(experiment).getByText('实验型功能')).toBeVisible();
  expect(within(experiment).getByRole('checkbox', { name: /论点论据一致性检测/ })).toBeChecked();
  expect(within(experiment).getByText('实验性')).toBeVisible();
  fireEvent.click(within(experiment).getByRole('button', { name: '全选论文逻辑审查' }));
  expect(within(experiment).getByRole('checkbox', { name: /论点论据一致性检测/ })).toBeChecked();
});

it('selects all fifteen available rules including logic review on a new upload', async () => {
  const ids = ['sjtu_rule_18', 'sjtu_rule_22', 'sjtu_rule_24', 'sjtu_rule_28', 'sjtu_rule_31',
    'required_section_completeness_check', 'keyword_count_check', 'abstract_object_number_check', 'chapter_new_page_check',
    'typo_detection_check', 'bilingual_abstract_consistency_check', 'chinese_english_symbol_mix_check',
    'bilingual_keywords_correspondence_check', 'sjtu_rule_32', 'abstract_numeric_consistency_check'];
  vi.mocked(fetchReviewPilotPaperLintRules).mockResolvedValue({ ...catalog, rules: ids.map(rule_id => ({
    ...rules[0], rule_id, title: rule_id, uses_external_model: rule_id === 'abstract_numeric_consistency_check',
  })) } as never);
  showUpload();
  expect(await screen.findByText('已选择全部检测规则')).toBeInTheDocument();
  expect(screen.getByText('15 / 15')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '展开选择' }));
  const selection = screen.getByRole('region', { name: '检测规则选择' });
  const checkboxes = within(selection).getAllByRole('checkbox');
  expect(checkboxes).toHaveLength(15);
  checkboxes.forEach(input => expect(input).toBeChecked());
  fireEvent.click(within(selection).getByRole('checkbox', { name: /论点论据一致性检测/ }));
  expect(screen.getByText('已选择 14 项检测规则')).toBeInTheDocument();
});

it.each([false, true])('updates the actual live report and preserves the selected finding (restored=%s)', async (restored) => {
  const ids = ['sjtu_rule_18', 'typo_detection_check'];
  const run = (rule_id: string, message: string) => ({ rule_id, rule_run_id: rule_id,
    severity: 'warning', execution_status: 'completed', outcome: 'issues_found',
    findings: [{ finding_id: rule_id, rule_id, message, location: null, anchors: [] }] });
  const first = run(ids[1], '先完成的错别字结果');
  const second = run(ids[0], '后完成的公式结果');
  let nextPoll!: (value: any) => void;
  vi.mocked(fetchPaperLintJob).mockResolvedValueOnce({ ...pendingJob, status: 'running', progress: {
    completed_rule_ids: [ids[1]], total_rule_ids: ids, rule_runs: [first],
  } } as never).mockImplementation(() => new Promise(resolve => { nextPoll = resolve; }));
  if (restored) localStorage.setItem('paper-lint-active-job:upload-student', JSON.stringify({
    jobId: pendingJob.job_id, requestId: 'restored', filename: '论文.pdf', selectedRuleIds: ids,
  }));
  showUpload();
  if (!restored) {
    await choosePdf();
    fireEvent.click(screen.getByRole('button', { name: '开始检测', exact: true }));
  }
  const region = await screen.findByRole('region', { name: '实时检测报告' });
  const ring = screen.getByRole('progressbar', { name: '检测进度' });
  expect(ring.querySelectorAll('svg circle')).toHaveLength(2);
  expect(ring).toHaveAttribute('aria-valuenow', '50');
  expect(ring.compareDocumentPosition(region) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(within(region).getByText('先完成的错别字结果')).toBeInTheDocument();
  expect(Array.from(within(region).getByRole('combobox', { name: '按检查项筛选' }).querySelectorAll('option')).map(option => option.value).sort())
    .toEqual(['all', ...(restored ? ids : rules.slice(0, 3).map(rule => rule.rule_id))].sort());
  expect(within(region).getByRole('heading', { name: '正文错别字检测', exact: true })).toBeInTheDocument();
  expect(within(region).queryByRole('heading', { name: /^规则\s*\d/ })).not.toBeInTheDocument();
  expect(within(region).queryByText('后完成的公式结果')).not.toBeInTheDocument();
  expect(screen.queryByRole('region', { name: '已完成规则结果' })).not.toBeInTheDocument();
  expect(within(region).getByText('错误总数').closest('div')).toHaveTextContent('1');
  fireEvent.click(within(region).getByText('先完成的错别字结果').closest('article')!);
  const preview = screen.getByLabelText('实时原文预览');
  expect(preview).toHaveAttribute('data-active', ids[1]);
  expect(preview).toHaveAttribute('data-source', restored ? '/api/normative/paper-lint/jobs/upload-job/pdf' : '论文.pdf');
  await waitFor(() => expect(nextPoll).toBeTypeOf('function'));
  await act(async () => nextPoll({ ...pendingJob, status: 'running', progress: {
    completed_rule_ids: [ids[1], ids[0]], total_rule_ids: ids, rule_runs: [first, second],
  } }));
  expect(within(region).getByText('后完成的公式结果')).toBeInTheDocument();
  expect(within(region).getByText('错误总数').closest('div')).toHaveTextContent('2');
  expect(screen.getByRole('progressbar', { name: '检测进度' })).toBe(ring);
  expect(ring).toHaveAttribute('aria-valuenow', '100');
  expect(screen.getByLabelText('实时原文预览')).toBe(preview);
  expect(preview).toHaveAttribute('data-active', ids[1]);
  expect(screen.getByRole('button', { name: '停止检测' })).toBeInTheDocument();
  expect(fetchPaperLintReport).not.toHaveBeenCalled();
});

it('keeps the original content group order and puts external references last', async () => {
  const ids = ['sjtu_rule_32', 'bilingual_keywords_correspondence_check', 'chinese_english_symbol_mix_check', 'bilingual_abstract_consistency_check', 'typo_detection_check'];
  vi.mocked(fetchReviewPilotPaperLintRules).mockResolvedValue({ ...catalog, rules: ids.map(rule_id => ({ ...rules[0], rule_id, title: rule_id })) } as never);
  showUpload();
  await screen.findByText('已选择全部检测规则');
  fireEvent.click(screen.getByRole('button', { name: '展开选择' }));
  expect(within(screen.getByRole('region', { name: '内容规范检测规则' })).getAllByRole('checkbox').map(input => input.closest('label')?.textContent)).toEqual([
    expect.stringContaining('typo_detection_check'),
    expect.stringContaining('bilingual_abstract_consistency_check'),
    expect.stringContaining('chinese_english_symbol_mix_check'),
    expect.stringContaining('bilingual_keywords_correspondence_check'),
    expect.stringContaining('sjtu_rule_32'),
  ]);
});
