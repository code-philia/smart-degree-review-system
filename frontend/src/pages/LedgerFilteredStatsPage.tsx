import { useMemo, useState } from 'react';
import {
  DetectionLedgerFilteredStats,
  DetectionLedgerType,
  LedgerRecordFilters,
  fetchDetectionLedgerFilteredStats,
} from '../api/normativeRules';

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

function LedgerFilteredStatsPage() {
  const [filters, setFilters] = useState<LedgerRecordFilters>(initialFilters);
  const [stats, setStats] = useState<DetectionLedgerFilteredStats | null>(null);
  const [status, setStatus] = useState<'idle' | 'loading' | 'error'>('idle');
  const [errorMessage, setErrorMessage] = useState('');

  const activeTypeLabel = useMemo(
    () => detectionTypeTabs.find((tab) => tab.value === filters.detection_type)?.label || '全部类型',
    [filters.detection_type],
  );

  async function refreshStats(nextFilters = filters) {
    setStatus('loading');
    setErrorMessage('');
    try {
      const nextStats = await fetchDetectionLedgerFilteredStats(nextFilters);
      setStats(nextStats);
      setStatus('idle');
    } catch (error) {
      setStatus('error');
      setErrorMessage(error instanceof Error ? error.message : '筛选统计加载失败');
    }
  }

  return (
    <main className="min-h-screen bg-[#eef3f8] text-[#1f2d3d]">
      <header className="flex h-[72px] items-center justify-center bg-[#1f3f63] text-[28px] font-bold text-white">
        学位论文检测台账管理
      </header>

      <section className="flex gap-3 px-7 py-3">
        <a className="h-12 rounded-[5px] border border-[#d6d6d6] bg-white px-10 py-2.5 text-[22px] font-bold text-[#7c8792]" href="/ledger-records">检测记录台账</a>
        <button className="h-12 rounded-[5px] bg-[#1f3f63] px-10 text-[22px] font-bold text-white">检测数据统计</button>
      </section>

      <section className="flex flex-wrap items-center justify-between gap-3 px-7 pb-3">
        <div className="flex flex-wrap gap-3">
          <button className="h-11 rounded-sm border border-[#3b86ee] bg-[#3b86ee] px-8 text-[17px] font-semibold text-white">筛选统计</button>
          <button className="h-11 rounded-sm border border-[#d6d6d6] bg-white px-8 text-[17px] font-semibold text-[#303b45]">每日趋势</button>
        </div>
        <p className="text-[#536476]">当前筛选记录数：<strong className="text-[#1f3f63]">{stats?.total_records ?? 0}</strong></p>
        <button className="h-11 bg-[#46c33f] px-10 font-bold text-white" type="button">导出报表</button>
      </section>

      <section className="mx-7 overflow-hidden rounded-sm border border-[#d6d6d6] bg-white">
        <h2 className="bg-[#1f3f63] px-5 py-3 text-[18px] font-bold text-white">筛选条件配置</h2>
        <div className="grid gap-4 bg-[#f8fafc] p-5 md:grid-cols-4">
          <label className="grid gap-2 text-[15px] font-semibold text-[#1f3f63]">
            时间范围
            <span className="flex items-center gap-2">
              <input className="h-11 w-full border border-[#d6d6d6] bg-white px-3 font-normal" type="date" value={filters.from || ''} onChange={(event) => setFilters((current) => ({ ...current, from: event.target.value }))} />
              ~
              <input className="h-11 w-full border border-[#d6d6d6] bg-white px-3 font-normal" type="date" value={filters.to || ''} onChange={(event) => setFilters((current) => ({ ...current, to: event.target.value }))} />
            </span>
          </label>
          <label className="grid gap-2 text-[15px] font-semibold text-[#1f3f63]">
            检测类型
            <select className="h-11 border border-[#d6d6d6] bg-white px-3 font-normal" value={filters.detection_type || ''} onChange={(event) => setFilters((current) => ({ ...current, detection_type: event.target.value as DetectionLedgerType | '' }))}>
              <option value="">全部类型</option>
              {detectionTypeTabs.map((tab) => <option key={tab.value} value={tab.value}>{tab.label}</option>)}
            </select>
          </label>
          <label className="grid gap-2 text-[15px] font-semibold text-[#1f3f63]">
            学生关键字
            <input className="h-11 border border-[#d6d6d6] bg-white px-3 font-normal" value={filters.student || ''} onChange={(event) => setFilters((current) => ({ ...current, student: event.target.value }))} placeholder="姓名或学号" />
          </label>
          <div className="flex items-end gap-3">
            <button className="h-11 border border-[#d6d6d6] bg-white px-8 font-bold text-[#303b45]" onClick={() => { setFilters(initialFilters); setStats(null); }}>重置</button>
            <button className="h-11 bg-[#3b86ee] px-10 font-bold text-white" onClick={() => void refreshStats()}>手动刷新</button>
          </div>
        </div>
      </section>

      <section className="grid gap-4 px-7 py-5 md:grid-cols-4">
        <article className="rounded-sm border border-[#d6d6d6] bg-white p-5"><p className="text-[#536476]">记录数</p><strong className="text-[30px] text-[#1f3f63]">{stats?.total_records ?? 0}</strong></article>
        <article className="rounded-sm border border-[#d6d6d6] bg-white p-5"><p className="text-[#536476]">参与学生数</p><strong className="text-[30px] text-[#1f3f63]">{stats?.total_students ?? 0}</strong></article>
        <article className="rounded-sm border border-[#d6d6d6] bg-white p-5"><p className="text-[#536476]">今日数量</p><strong className="text-[30px] text-[#1f3f63]">{stats?.today_count ?? 0}</strong></article>
        <article className="rounded-sm border border-[#d6d6d6] bg-white p-5"><p className="text-[#536476]">当前类型</p><strong className="text-[22px] text-[#1f3f63]">{activeTypeLabel}</strong></article>
      </section>

      <section className="grid gap-5 px-7 pb-8 lg:grid-cols-2">
        <article className="min-h-[280px] rounded-sm border border-[#d6d6d6] bg-white p-5">
          <h3 className="mb-4 text-[18px] font-bold text-[#1f3f63]">任务类型柱状图</h3>
          {status === 'loading' && <p className="py-16 text-center text-[#536476]">统计加载中...</p>}
          {status === 'error' && <p className="py-16 text-center text-red-600">{errorMessage}</p>}
          {status === 'idle' && !stats && <p className="py-16 text-center text-[#536476]">请选择筛选条件后手动刷新生成图表</p>}
          {stats && <div className="flex h-44 items-end gap-4 border-l border-b border-[#d6d6d6] px-4">{stats.by_type.map((item) => <div key={item.detection_type} className="flex flex-1 flex-col items-center gap-2"><div className="w-full bg-[#3b86ee]" style={{ height: `${Math.max(item.record_count, 1) * 8}px` }} /><span className="text-xs text-[#536476]">{item.detection_type_label}</span></div>)}</div>}
        </article>
        <article className="min-h-[280px] rounded-sm border border-[#d6d6d6] bg-white p-5">
          <h3 className="mb-4 text-[18px] font-bold text-[#1f3f63]">每日趋势折线图</h3>
          {stats ? <svg className="h-44 w-full border-l border-b border-[#d6d6d6]" role="img" aria-label="每日趋势折线图" /> : <p className="py-16 text-center text-[#536476]">暂无趋势数据</p>}
        </article>
      </section>
    </main>
  );
}

export default LedgerFilteredStatsPage;
