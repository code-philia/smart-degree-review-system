import apiClient from '../src/api';
import {
  downloadDetectionLedgerCsv,
  fetchDetectionLedgerRecord,
  fetchDetectionLedgerRecords,
  type DetectionLedgerRecord,
} from '../src/api/normativeRules';
import { describe, expect, it, vi } from 'vitest';

const REQ_ID = 'FEAT-LEDGER-RECORDS';
void REQ_ID;

const record: DetectionLedgerRecord = {
  id: 'ledger-client-001',
  source_record_id: 'source-client-001',
  college_id: 'college01',
  college_name: '信息学院',
  student_id: 'student01',
  student_number: '2024001',
  student_name: '张三',
  supervisor_id: 'supervisor01',
  supervisor_name: '李导师',
  student_category: '硕士',
  thesis_title: '台账客户端论文',
  detection_type: 'normative',
  detection_type_label: '规范性检测',
  template_name: '规范性模板A',
  core_result: '错误数 2',
  detail_url: '/normative-reports/ledger-client-001',
  is_latest: true,
  created_at: '2026-08-04T10:00:00.000Z',
};

describe('FEAT-LEDGER-RECORDS API client contract', () => {
  it('FEAT-LEDGER-RECORDS:API:001 serializes ledger filters through the shared Axios client for list, detail, and export', async () => {
    const getSpy = vi.spyOn(apiClient, 'get');
    getSpy.mockResolvedValueOnce({ data: { records: [record] } });
    getSpy.mockResolvedValueOnce({ data: record });
    getSpy.mockResolvedValueOnce({ data: new Blob(['csv'], { type: 'text/csv' }) });

    await expect(
      fetchDetectionLedgerRecords({ student: 'student01', detection_type: 'normative', from: '2026-08-01', to: '2026-08-31', latest_only: true }),
    ).resolves.toEqual([record]);
    await expect(fetchDetectionLedgerRecord('ledger-client-001')).resolves.toEqual(record);
    await expect(
      downloadDetectionLedgerCsv({ student: 'student01', detection_type: 'normative', from: '2026-08-01', to: '2026-08-31', latest_only: true }),
    ).resolves.toBeInstanceOf(Blob);

    expect(getSpy).toHaveBeenNthCalledWith(1, '/normative/ledger-records', {
      params: {
        student: 'student01',
        detection_type: 'normative',
        from: '2026-08-01',
        to: '2026-08-31',
        latest_only: 'true',
      },
    });
    expect(getSpy).toHaveBeenNthCalledWith(2, '/normative/ledger-records/ledger-client-001');
    expect(getSpy).toHaveBeenNthCalledWith(3, '/normative/ledger-records/export.csv', {
      params: {
        student: 'student01',
        detection_type: 'normative',
        from: '2026-08-01',
        to: '2026-08-31',
        latest_only: 'true',
      },
      responseType: 'blob',
      headers: { Accept: 'text/csv' },
    });
    expect(apiClient.defaults.withCredentials).toBe(true);
    expect(apiClient.defaults.baseURL).toBe('/api');
    expect(apiClient.interceptors.response).toBeDefined();

    getSpy.mockRestore();
  });
});
