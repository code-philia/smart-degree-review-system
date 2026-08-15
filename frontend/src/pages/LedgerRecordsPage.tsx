import { useEffect, useMemo, useState } from 'react';
import {
  DetectionLedgerRecord,
  DetectionLedgerType,
  LedgerRecordFilters,
  downloadDetectionLedgerCsv,
  fetchDetectionLedgerRecords,
} from '../api/normativeRules';
import {
  DataTable,
  DataTableCell,
  DataTableHead,
  DataTableRow,
  EmptyState,
  ErrorState,
  LoadingState,
} from '../components/ui';

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

      <DataTable tableClassName="min-w-[1180px] table-fixed" aria-label="检测记录台账">
        <thead>
          <DataTableRow className="hover:bg-transparent">
            <DataTableHead className="w-12 text-center">
              <input
                type="checkbox"
                checked={allSelected}
                onChange={(event) => setSelectedIds(event.target.checked ? records.map((record) => record.id) : [])}
              />
            </DataTableHead>
            <DataTableHead className="w-28 text-center">学院</DataTableHead>
            <DataTableHead className="w-28 text-center">学号</DataTableHead>
            <DataTableHead className="w-24 text-center">姓名</DataTableHead>
            <DataTableHead className="w-24 text-center">导师</DataTableHead>
            <DataTableHead className="w-28 text-center">学生类别</DataTableHead>
            <DataTableHead className="w-64">论文题目</DataTableHead>
            <DataTableHead className="w-28 text-center">检测类型</DataTableHead>
            <DataTableHead className="w-28 text-center">检测模板</DataTableHead>
            <DataTableHead className="w-24 text-center">核心结果</DataTableHead>
            <DataTableHead className="w-24 text-center">检测报告</DataTableHead>
            <DataTableHead className="w-40 text-center">检测时间</DataTableHead>
          </DataTableRow>
        </thead>
        <tbody>
          {status === 'loading' && (
            <DataTableRow>
              <DataTableCell className="py-8" colSpan={12}>
                <LoadingState compact label="加载中..." />
              </DataTableCell>
            </DataTableRow>
          )}
          {status === 'error' && (
            <DataTableRow>
              <DataTableCell className="py-8" colSpan={12}>
                <ErrorState message={errorMessage} onRetry={() => void loadRecords()} />
              </DataTableCell>
            </DataTableRow>
          )}
          {status === 'idle' && records.length === 0 && (
            <DataTableRow>
              <DataTableCell className="py-8" colSpan={12}>
                <EmptyState title="暂无符合条件的台账记录" />
              </DataTableCell>
            </DataTableRow>
          )}
          {records.map((record) => (
            <DataTableRow key={record.id} className="h-14">
              <DataTableCell className="text-center">
                <input
                  type="checkbox"
                  checked={selectedIds.includes(record.id)}
                  onChange={(event) =>
                    setSelectedIds((current) =>
                      event.target.checked ? [...current, record.id] : current.filter((id) => id !== record.id),
                    )
                  }
                />
              </DataTableCell>
              <DataTableCell className="text-center">{record.college_name}</DataTableCell>
              <DataTableCell className="text-center">{record.student_number}</DataTableCell>
              <DataTableCell className="text-center">{record.student_name}</DataTableCell>
              <DataTableCell className="text-center">{record.supervisor_name}</DataTableCell>
              <DataTableCell className="text-center">{record.student_category}</DataTableCell>
              <DataTableCell className="font-semibold text-slate-900">{record.thesis_title}</DataTableCell>
              <DataTableCell className="text-center">{record.detection_type_label}</DataTableCell>
              <DataTableCell className="text-center">{record.template_name}</DataTableCell>
              <DataTableCell className="text-center font-semibold text-warning-600">{record.core_result}</DataTableCell>
              <DataTableCell className="text-center">
                <a className="font-semibold text-brand-600 hover:text-brand-700" href={record.detail_url}>
                  详情
                </a>
              </DataTableCell>
              <DataTableCell className="text-center tabular-nums">{record.created_at}</DataTableCell>
            </DataTableRow>
          ))}
        </tbody>
      </DataTable>
    </div>
  );
}

export default LedgerRecordsPage;
