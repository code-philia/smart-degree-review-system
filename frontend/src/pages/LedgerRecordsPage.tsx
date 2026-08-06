import { useEffect, useMemo, useState } from 'react';
import {
  DetectionLedgerRecord,
  DetectionLedgerType,
  LedgerRecordFilters,
  downloadDetectionLedgerCsv,
  fetchDetectionLedgerRecords,
} from '../api/normativeRules';
import { EmptyState, ErrorState, LoadingState } from '../components/ui';

const detectionTypeTabs: Array<{ value: DetectionLedgerType | ''; label: string }> = [
  { value: 'normative', label: '规范性检测' },
  { value: 'aigc', label: 'AIGC查重' },
  { value: 'duplication', label: '校内库查重' },
  { value: 'polish', label: '全文润色' },
  { value: 'innovation', label: '创新性分析' },
  { value: 'ai_review', label: 'AI智能评阅' },
];

const initialFilters: LedgerRecordFilters = {
  detection_type: 'normative',
  latest_only: false,
};

function LedgerRecordsPage() {
  const [filters, setFilters] = useState<LedgerRecordFilters>(initialFilters);
  const [records, setRecords] = useState<DetectionLedgerRecord[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [status, setStatus] = useState<'idle' | 'loading' | 'error'>('idle');
  const [errorMessage, setErrorMessage] = useState('');

  const allSelected = records.length > 0 && selectedIds.length === records.length;
  const activeTypeLabel = useMemo(
    () => detectionTypeTabs.find((tab) => tab.value === filters.detection_type)?.label || '全部类型',
    [filters.detection_type],
  );

  async function loadRecords(nextFilters = filters) {
    setStatus('loading');
    setErrorMessage('');
    try {
      const nextRecords = await fetchDetectionLedgerRecords(nextFilters);
      setRecords(nextRecords);
      setSelectedIds([]);
      setStatus('idle');
    } catch (error) {
      setStatus('error');
      setErrorMessage(error instanceof Error ? error.message : '台账记录加载失败');
    }
  }

  useEffect(() => {
    void loadRecords(initialFilters);
  }, []);

  async function handleExport() {
    await downloadDetectionLedgerCsv(filters);
  }

  return (
    <div>
      <p className="mb-4 text-2xl font-black text-[#1f3f63]">学位论文检测台账管理</p>

      <section className="flex gap-3 py-3">
        <button className="h-12 rounded-[5px] bg-[#1f3f63] px-10 text-[22px] font-bold text-white">检测记录台账</button>
        <a
          className="h-12 rounded-[5px] border border-[#d6d6d6] bg-white px-10 py-2.5 text-[22px] font-bold text-[#7c8792]"
          href="/ledger-stats"
        >
          检测数据统计
        </a>
      </section>

      <section className="grid grid-cols-2 gap-3 pb-3 md:grid-cols-6">
        {detectionTypeTabs.map((tab) => (
          <button
            key={tab.label}
            className={`h-11 rounded-sm border text-[17px] font-semibold ${filters.detection_type === tab.value ? 'border-[#3b86ee] bg-[#3b86ee] text-white' : 'border-[#d6d6d6] bg-white text-[#303b45]'}`}
            onClick={() => setFilters((current) => ({ ...current, detection_type: tab.value }))}
          >
            {tab.label}
          </button>
        ))}
      </section>

      <section className="grid gap-4 py-4 md:grid-cols-4">
        <label className="grid gap-2 text-[16px] font-semibold text-[#1f3f63]">
          学生
          <input
            className="h-11 border border-[#d6d6d6] bg-white px-3 font-normal"
            value={filters.student || ''}
            onChange={(event) => setFilters((current) => ({ ...current, student: event.target.value }))}
          />
        </label>
        <label className="grid gap-2 text-[16px] font-semibold text-[#1f3f63]">
          检测类型
          <input className="h-11 border border-[#d6d6d6] bg-white px-3 font-normal" value={activeTypeLabel} readOnly />
        </label>
        <label className="grid gap-2 text-[16px] font-semibold text-[#1f3f63]">
          开始时间
          <input
            className="h-11 border border-[#d6d6d6] bg-white px-3 font-normal"
            type="date"
            value={filters.from || ''}
            onChange={(event) => setFilters((current) => ({ ...current, from: event.target.value }))}
          />
        </label>
        <label className="grid gap-2 text-[16px] font-semibold text-[#1f3f63]">
          结束时间
          <input
            className="h-11 border border-[#d6d6d6] bg-white px-3 font-normal"
            type="date"
            value={filters.to || ''}
            onChange={(event) => setFilters((current) => ({ ...current, to: event.target.value }))}
          />
        </label>
        <label className="flex items-center gap-2 text-[16px] font-semibold text-[#1f3f63]">
          <input
            type="checkbox"
            checked={Boolean(filters.latest_only)}
            onChange={(event) => setFilters((current) => ({ ...current, latest_only: event.target.checked }))}
          />
          最新检测
        </label>
        <div className="flex gap-3 md:col-span-3 md:justify-end">
          <button className="h-11 bg-[#3b86ee] px-10 font-bold text-white" onClick={() => void loadRecords()}>
            查询
          </button>
          <button
            className="h-11 border border-[#d6d6d6] bg-white px-10 font-bold text-[#303b45]"
            onClick={() => {
              setFilters(initialFilters);
              void loadRecords(initialFilters);
            }}
          >
            重置
          </button>
        </div>
      </section>

      <section className="flex items-center justify-between border-y border-[#e5e5e5] bg-white py-3">
        <p className="text-[#536476]">
          共 {records.length} 条记录，已选择 {selectedIds.length} 条
        </p>
        <button className="h-12 bg-[#46c33f] px-12 font-bold text-white" onClick={() => void handleExport()}>
          导出
        </button>
      </section>

      <section className="overflow-x-auto bg-white pb-8">
        <table className="min-w-[1180px] table-fixed border-collapse text-[15px]">
          <thead className="bg-[#1f3f63] text-white">
            <tr>
              <th className="w-12 border border-[#e5e5e5] py-3">
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={(event) => setSelectedIds(event.target.checked ? records.map((record) => record.id) : [])}
                />
              </th>
              <th className="w-28 border border-[#e5e5e5]">学院</th>
              <th className="w-28 border border-[#e5e5e5]">学号</th>
              <th className="w-24 border border-[#e5e5e5]">姓名</th>
              <th className="w-24 border border-[#e5e5e5]">导师</th>
              <th className="w-28 border border-[#e5e5e5]">学生类别</th>
              <th className="w-64 border border-[#e5e5e5]">论文题目</th>
              <th className="w-28 border border-[#e5e5e5]">检测类型</th>
              <th className="w-28 border border-[#e5e5e5]">检测模板</th>
              <th className="w-24 border border-[#e5e5e5]">核心结果</th>
              <th className="w-24 border border-[#e5e5e5]">检测报告</th>
              <th className="w-40 border border-[#e5e5e5]">检测时间</th>
            </tr>
          </thead>
          <tbody>
            {status === 'loading' && (
              <tr>
                <td className="border border-[#e5e5e5] py-8" colSpan={12}>
                  <LoadingState compact label="加载中..." />
                </td>
              </tr>
            )}
            {status === 'error' && (
              <tr>
                <td className="border border-[#e5e5e5] py-8" colSpan={12}>
                  <ErrorState message={errorMessage} onRetry={() => void loadRecords()} />
                </td>
              </tr>
            )}
            {status === 'idle' && records.length === 0 && (
              <tr>
                <td className="border border-[#e5e5e5] py-8" colSpan={12}>
                  <EmptyState title="暂无符合条件的台账记录" />
                </td>
              </tr>
            )}
            {records.map((record) => (
              <tr key={record.id} className="h-[74px]">
                <td className="border border-[#e5e5e5] text-center">
                  <input
                    type="checkbox"
                    checked={selectedIds.includes(record.id)}
                    onChange={(event) =>
                      setSelectedIds((current) =>
                        event.target.checked ? [...current, record.id] : current.filter((id) => id !== record.id),
                      )
                    }
                  />
                </td>
                <td className="border border-[#e5e5e5] text-center">{record.college_name}</td>
                <td className="border border-[#e5e5e5] text-center">{record.student_number}</td>
                <td className="border border-[#e5e5e5] text-center">{record.student_name}</td>
                <td className="border border-[#e5e5e5] text-center">{record.supervisor_name}</td>
                <td className="border border-[#e5e5e5] text-center">{record.student_category}</td>
                <td className="border border-[#e5e5e5] px-3">{record.thesis_title}</td>
                <td className="border border-[#e5e5e5] text-center">{record.detection_type_label}</td>
                <td className="border border-[#e5e5e5] text-center">{record.template_name}</td>
                <td className="border border-[#e5e5e5] text-center font-semibold text-[#e98332]">
                  {record.core_result}
                </td>
                <td className="border border-[#e5e5e5] text-center">
                  <a className="text-[#3b86ee]" href={record.detail_url}>
                    详情
                  </a>
                </td>
                <td className="border border-[#e5e5e5] text-center">{record.created_at}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

export default LedgerRecordsPage;
