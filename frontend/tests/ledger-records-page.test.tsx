import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import LedgerRecordsPage from '../src/pages/LedgerRecordsPage';
import {
  downloadDetectionLedgerCsv,
  fetchDetectionLedgerRecords,
  type DetectionLedgerRecord,
} from '../src/api/normativeRules';

vi.mock('../src/api/normativeRules', async () => {
  const actual = await vi.importActual<typeof import('../src/api/normativeRules')>('../src/api/normativeRules');
  return {
    ...actual,
    downloadDetectionLedgerCsv: vi.fn(),
    fetchDetectionLedgerRecords: vi.fn(),
  };
});

const REQ_ID = 'FEAT-LEDGER-RECORDS';
void REQ_ID;

const firstRecord: DetectionLedgerRecord = {
  id: 'ledger-ui-001',
  source_record_id: 'source-ui-001',
  college_id: 'college01',
  college_name: '信息学院',
  student_id: 'student01',
  student_number: '2024001',
  student_name: '张三',
  supervisor_id: 'supervisor01',
  supervisor_name: '李导师',
  student_category: '硕士',
  thesis_title: '台账页面论文一号',
  detection_type: 'normative',
  detection_type_label: '规范性检测',
  template_name: '规范性模板A',
  core_result: '错误数 2',
  detail_url: '/normative-reports/ledger-ui-001',
  is_latest: true,
  created_at: '2026-08-04T10:00:00.000Z',
};

const secondRecord: DetectionLedgerRecord = {
  ...firstRecord,
  id: 'ledger-ui-002',
  source_record_id: 'source-ui-002',
  student_number: '2024002',
  student_name: '李四',
  thesis_title: '台账页面论文二号',
  core_result: '错误数 0',
  detail_url: '/normative-reports/ledger-ui-002',
  created_at: '2026-08-05T11:30:00.000Z',
};

function renderPage() {
  return render(<LedgerRecordsPage />);
}

describe('FEAT-LEDGER-RECORDS ledger page contract', () => {
  beforeEach(() => {
    vi.mocked(fetchDetectionLedgerRecords).mockReset();
    vi.mocked(downloadDetectionLedgerCsv).mockReset();
  });

  it('FEAT-LEDGER-RECORDS:UI:001 renders the backend-driven ledger shell and runtime rows without screenshot data', async () => {
    vi.mocked(fetchDetectionLedgerRecords).mockResolvedValueOnce([firstRecord, secondRecord]);

    renderPage();

    expect(screen.getByText('学位论文检测台账管理')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '检测记录台账' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '检测数据统计' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '规范性检测' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'AIGC查重' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '查询' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重置' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '导出' })).toBeInTheDocument();

    await waitFor(() => expect(fetchDetectionLedgerRecords).toHaveBeenCalledTimes(1));
    expect(fetchDetectionLedgerRecords).toHaveBeenCalledWith({ detection_type: 'normative', latest_only: false });

    const table = screen.getByRole('table');
    expect(within(table).getByRole('columnheader', { name: '学院' })).toBeInTheDocument();
    expect(within(table).getByRole('columnheader', { name: '检测报告' })).toBeInTheDocument();
    const rows = within(table).getAllByRole('row');
    expect(rows).toHaveLength(3);
    expect(within(rows[1]).getByText('信息学院')).toBeInTheDocument();
    expect(within(rows[1]).getByText('2024001')).toBeInTheDocument();
    expect(within(rows[1]).getByText('张三')).toBeInTheDocument();
    expect(within(rows[1]).getByText('李导师')).toBeInTheDocument();
    expect(within(rows[1]).getByText('台账页面论文一号')).toBeInTheDocument();
    expect(within(rows[1]).getByText('规范性检测')).toBeInTheDocument();
    expect(within(rows[1]).getByRole('link', { name: '详情' })).toHaveAttribute('href', '/normative-reports/ledger-ui-001');
    expect(within(rows[2]).getByText('台账页面论文二号')).toBeInTheDocument();
    expect(within(rows[2]).getByRole('link', { name: '详情' })).toHaveAttribute('href', '/normative-reports/ledger-ui-002');
    expect(screen.getByText('共 2 条记录，已选择 0 条')).toBeInTheDocument();
  });

  it('FEAT-LEDGER-RECORDS:UI:002 supports student, type, time, latest filters and exports the active CSV result set', async () => {
    vi.mocked(fetchDetectionLedgerRecords)
      .mockResolvedValueOnce([firstRecord, secondRecord])
      .mockResolvedValueOnce([secondRecord])
      .mockResolvedValueOnce([secondRecord]);
    vi.mocked(downloadDetectionLedgerCsv).mockResolvedValue(new Blob(['csv'], { type: 'text/csv' }));
    const user = userEvent.setup();

    renderPage();

    await waitFor(() => expect(screen.getByText('共 2 条记录，已选择 0 条')).toBeInTheDocument());
    expect(screen.getAllByRole('row')).toHaveLength(3);

    await user.clear(screen.getByLabelText('学生'));
    await user.type(screen.getByLabelText('学生'), 'student01');
    await user.click(screen.getByRole('button', { name: '全文润色' }));
    await user.clear(screen.getByLabelText('开始时间'));
    await user.type(screen.getByLabelText('开始时间'), '2026-08-01');
    await user.clear(screen.getByLabelText('结束时间'));
    await user.type(screen.getByLabelText('结束时间'), '2026-08-31');
    await user.click(screen.getByLabelText('最新检测'));
    await user.click(screen.getByRole('button', { name: '查询' }));

    await waitFor(() => expect(fetchDetectionLedgerRecords).toHaveBeenCalledTimes(2));
    expect(fetchDetectionLedgerRecords).toHaveBeenLastCalledWith({
      student: 'student01',
      detection_type: 'polish',
      from: '2026-08-01',
      to: '2026-08-31',
      latest_only: true,
    });
    expect(screen.getByText('共 1 条记录，已选择 0 条')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '详情' })).toHaveAttribute('href', '/normative-reports/ledger-ui-002');

    await user.click(screen.getByRole('button', { name: '导出' }));
    await waitFor(() => expect(downloadDetectionLedgerCsv).toHaveBeenCalledTimes(1));
    expect(downloadDetectionLedgerCsv).toHaveBeenCalledWith({
      student: 'student01',
      detection_type: 'polish',
      from: '2026-08-01',
      to: '2026-08-31',
      latest_only: true,
    });
  });

  it('FEAT-LEDGER-RECORDS:UI:EMPTY:001 shows explicit empty and error states without fallback rows', async () => {
    vi.mocked(fetchDetectionLedgerRecords)
      .mockResolvedValueOnce([])
      .mockRejectedValueOnce(new Error('台账记录加载失败'));

    renderPage();

    expect(await screen.findByText('暂无符合条件的台账记录')).toBeInTheDocument();
    expect(screen.getByText('共 0 条记录，已选择 0 条')).toBeInTheDocument();
    expect(screen.queryByText('台账页面论文一号')).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: '查询' }));
    expect(await screen.findByText('台账记录加载失败')).toBeInTheDocument();
  });
});
