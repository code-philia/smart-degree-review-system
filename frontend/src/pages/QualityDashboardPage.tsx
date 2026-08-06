import { useState } from 'react';
import {
  LedgerRecordFilters,
  QualityDashboardResponse,
  fetchQualityDashboard,
} from '../api/normativeRules';

const initialFilters: LedgerRecordFilters = {
  latest_only: true,
};

function formatScore(score: number | null) {
  return score === null ? '暂无数据' : score.toFixed(1);
}

function QualityDashboardPage() {
  const [filters, setFilters] = useState<LedgerRecordFilters>(initialFilters);
  const [dashboard, setDashboard] = useState<QualityDashboardResponse | null>(null);
  const [status, setStatus] = useState<'idle' | 'loading' | 'error'>('idle');
  const [errorMessage, setErrorMessage] = useState('');

  async function refreshDashboard(nextFilters = filters) {
    setStatus('loading');
    setErrorMessage('');
    try {
      const nextDashboard = await fetchQualityDashboard(nextFilters);
      setDashboard(nextDashboard);
      setStatus('idle');
    } catch (error) {
      setStatus('error');
      setErrorMessage(error instanceof Error ? error.message : '质量仪表盘加载失败');
    }
  }

  return (
    <div className="text-[#1f2d3d]">
      <section className="mb-5 overflow-hidden rounded-lg border border-[#d6d6d6] bg-white">
        <h2 className="bg-[#1f3f63] px-5 py-3 text-[18px] font-bold text-white">筛选条件</h2>
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
            学生关键字
            <input className="h-11 border border-[#d6d6d6] bg-white px-3 font-normal" value={filters.student || ''} onChange={(event) => setFilters((current) => ({ ...current, student: event.target.value }))} placeholder="姓名或学号" />
          </label>
          <label className="grid gap-2 text-[15px] font-semibold text-[#1f3f63]">
            类型
            <select className="h-11 border border-[#d6d6d6] bg-white px-3 font-normal" value={filters.detection_type || ''} onChange={(event) => setFilters((current) => ({ ...current, detection_type: event.target.value as LedgerRecordFilters['detection_type'] }))}>
              <option value="">全部质量项</option>
              <option value="normative">规范性检测</option>
              <option value="duplication">校内库查重</option>
              <option value="innovation">创新性分析</option>
              <option value="ai_review">AI智能评阅</option>
            </select>
          </label>
          <div className="flex items-end gap-3">
            <button className="h-11 border border-[#d6d6d6] bg-white px-8 font-bold text-[#303b45]" type="button" onClick={() => { setFilters(initialFilters); setDashboard(null); }}>重置</button>
            <button className="h-11 bg-[#3b86ee] px-10 font-bold text-white" type="button" onClick={() => void refreshDashboard()}>生成仪表盘</button>
          </div>
        </div>
      </section>

      {status === 'loading' && <p className="py-16 text-center text-[#536476]">质量数据加载中...</p>}
      {status === 'error' && <p className="py-16 text-center text-red-600">{errorMessage}</p>}
      {status === 'idle' && !dashboard && <p className="py-16 text-center text-[#536476]">请选择筛选条件后生成群体质量仪表盘</p>}

      {dashboard && (
        <>
          <section className="grid gap-4 px-7 pb-5 md:grid-cols-5">
            <article className="rounded-sm border border-[#d6d6d6] bg-white p-5"><p className="text-[#536476]">样本数</p><strong className="text-[30px] text-[#1f3f63]">{dashboard.sample_count}</strong></article>
            {dashboard.metrics.map((metric) => <article key={metric.key} className="rounded-sm border border-[#d6d6d6] bg-white p-5"><p className="text-[#536476]">{metric.label}</p><strong className="text-[26px] text-[#1f3f63]">{formatScore(metric.average_score)}</strong><p className="mt-2 text-sm text-[#536476]">有效 {metric.sample_count}，缺失 {metric.missing_count}</p></article>)}
          </section>

          <section className="grid gap-5 px-7 pb-8 lg:grid-cols-2">
            <article className="rounded-sm border border-[#d6d6d6] bg-white p-5">
              <h3 className="mb-4 text-[18px] font-bold text-[#1f3f63]">四指标分布图</h3>
              {dashboard.metrics.every((metric) => metric.distribution.length === 0) ? <p className="py-16 text-center text-[#536476]">暂无分布数据</p> : dashboard.metrics.map((metric) => <div key={metric.key} className="mb-4"><p className="mb-2 font-semibold text-[#1f3f63]">{metric.label}</p><div className="flex h-20 items-end gap-2 border-l border-b border-[#d6d6d6] px-3">{metric.distribution.map((bucket) => <div key={bucket.range} className="flex flex-1 flex-col items-center gap-1"><div className="w-full bg-[#3b86ee]" style={{ height: `${Math.max(bucket.count, 1) * 8}px` }} /><span className="text-xs text-[#536476]">{bucket.range}</span></div>)}</div></div>)}
            </article>

            <article className="rounded-sm border border-[#d6d6d6] bg-white p-5">
              <h3 className="mb-4 text-[18px] font-bold text-[#1f3f63]">学生质量明细</h3>
              {dashboard.students.length === 0 ? <p className="py-16 text-center text-[#536476]">当前筛选条件下暂无学生质量数据</p> : <div className="overflow-auto"><table className="w-full min-w-[640px] border-collapse text-left"><thead><tr className="bg-[#f8fafc] text-[#1f3f63]"><th className="border border-[#d6d6d6] p-3">学生</th><th className="border border-[#d6d6d6] p-3">规范分</th><th className="border border-[#d6d6d6] p-3">原创参考分</th><th className="border border-[#d6d6d6] p-3">创新参考分</th><th className="border border-[#d6d6d6] p-3">评阅基础分</th></tr></thead><tbody>{dashboard.students.map((student) => <tr key={student.student_id}><td className="border border-[#d6d6d6] p-3">{student.student_name}</td><td className="border border-[#d6d6d6] p-3">{formatScore(student.scores.normative)}</td><td className="border border-[#d6d6d6] p-3">{formatScore(student.scores.originality)}</td><td className="border border-[#d6d6d6] p-3">{formatScore(student.scores.innovation)}</td><td className="border border-[#d6d6d6] p-3">{formatScore(student.scores.review_base)}</td></tr>)}</tbody></table></div>}
            </article>
          </section>
        </>
      )}
    </div>
  );
}

export default QualityDashboardPage;
