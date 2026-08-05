import { useEffect, useState } from 'react';
import {
  fetchSupervisorReviewQueue,
  type SupervisorReviewQueueFilters,
  type SupervisorReviewQueueItem,
  type SupervisorReviewQueueResponse,
} from '../api/reportSupervisorQueue';
import type { ReportSubmissionSourceType } from '../api/reportSubmissions';

const sourceLabels: Record<ReportSubmissionSourceType, string> = {
  normative: '规范检测',
  duplication: '相似度检测',
  innovation: '创新性评价',
  ai_review: 'AI 评阅',
};

const statusLabels = {
  pending: '待批阅',
  done: '已完成',
};

function formatDateTime(value: string) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', { hour12: false });
}

export default function SupervisorReviewQueuePage() {
  const [filters, setFilters] = useState<SupervisorReviewQueueFilters>({});
  const [data, setData] = useState<SupervisorReviewQueueResponse>({ records: [], unread_count: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    fetchSupervisorReviewQueue(filters)
      .then((response) => {
        if (!active) return;
        setData(response);
      })
      .catch(() => {
        if (!active) return;
        setData({ records: [], unread_count: 0 });
        setError('待批阅任务加载失败，请确认导师身份后重试');
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [filters]);

  function updateFilter<Key extends keyof SupervisorReviewQueueFilters>(key: Key, value: string) {
    setFilters((current) => ({ ...current, [key]: value || undefined }));
  }

  return (
    <main className="min-h-screen bg-[#f5f7fa] text-slate-900">
      <header className="flex h-[72px] items-center justify-between bg-[#1f3f67] px-8 text-white">
        <div>
          <p className="text-sm font-semibold text-blue-100">导师站内批阅中心</p>
          <h1 className="text-2xl font-bold">待批阅任务</h1>
        </div>
        <div className="relative rounded-xl bg-[#173a62] px-5 py-3 text-sm font-bold">
          未完成待办
          <span className="ml-3 rounded-full bg-red-500 px-3 py-1 text-white">{data.unread_count}</span>
        </div>
      </header>

      <section className="m-6 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-wrap items-center gap-3 border-b border-slate-200 px-5 py-4 text-sm">
          <label className="font-semibold text-slate-700">
            学生
            <input
              value={filters.student_id || ''}
              onChange={(event) => updateFilter('student_id', event.target.value)}
              className="ml-2 rounded border border-slate-300 px-3 py-2"
              placeholder="学生账号"
            />
          </label>
          <label className="font-semibold text-slate-700">
            报告类型
            <select
              value={filters.source_type || ''}
              onChange={(event) => updateFilter('source_type', event.target.value)}
              className="ml-2 rounded border border-slate-300 px-3 py-2"
            >
              <option value="">全部</option>
              {Object.entries(sourceLabels).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </label>
          <label className="font-semibold text-slate-700">
            状态
            <select
              value={filters.status || ''}
              onChange={(event) => updateFilter('status', event.target.value)}
              className="ml-2 rounded border border-slate-300 px-3 py-2"
            >
              <option value="">全部</option>
              <option value="pending">待批阅</option>
              <option value="done">已完成</option>
            </select>
          </label>
          <span className="ml-auto text-slate-500">按待批阅优先、提交时间倒序展示本人待办。</span>
        </div>

        <div className="p-5">
          {error ? <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div> : null}
          {loading ? (
            <div className="rounded-lg border border-dashed border-slate-300 px-4 py-12 text-center text-slate-500">正在加载待批阅任务...</div>
          ) : data.records.length === 0 ? (
            <div className="rounded-lg border border-dashed border-slate-300 px-4 py-12 text-center text-slate-500">暂无待批阅任务。</div>
          ) : (
            <table className="w-full border-collapse overflow-hidden rounded-lg text-sm">
              <thead className="bg-[#1f3f67] text-white">
                <tr>
                  <th className="border border-[#173a62] px-4 py-3">状态</th>
                  <th className="border border-[#173a62] px-4 py-3">学生</th>
                  <th className="border border-[#173a62] px-4 py-3">报告类型</th>
                  <th className="border border-[#173a62] px-4 py-3">报告编号</th>
                  <th className="border border-[#173a62] px-4 py-3">标题</th>
                  <th className="border border-[#173a62] px-4 py-3">提交时间</th>
                </tr>
              </thead>
              <tbody>
                {data.records.map((record: SupervisorReviewQueueItem) => (
                  <tr key={record.todo_id} className="odd:bg-white even:bg-slate-50">
                    <td className="border border-slate-200 px-4 py-3 font-semibold text-[#ff8f2a]">{statusLabels[record.todo_status]}</td>
                    <td className="border border-slate-200 px-4 py-3">{record.student_id}</td>
                    <td className="border border-slate-200 px-4 py-3">{sourceLabels[record.source_type]}</td>
                    <td className="border border-slate-200 px-4 py-3 font-mono text-xs">{record.report_id}</td>
                    <td className="border border-slate-200 px-4 py-3">{record.title}</td>
                    <td className="border border-slate-200 px-4 py-3">{formatDateTime(record.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>
    </main>
  );
}
