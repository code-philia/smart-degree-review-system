import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  fetchSupervisorReviewQueue,
  type SupervisorReviewQueueFilters,
  type SupervisorReviewQueueItem,
  type SupervisorReviewQueueResponse,
} from '../api/reportSupervisorQueue';
import type { ReportSubmissionSourceType } from '../api/reportSubmissions';
import {
  DataTable,
  DataTableCell,
  DataTableHead,
  DataTableRow,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
} from '../components/ui';

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
    <div className="text-slate-900">
      <PageHeader
        title="待批阅任务"
        description="导师站内批阅中心，按待批阅优先、提交时间倒序展示本人待办。"
        actions={
          <div className="relative rounded-xl bg-[#173a62] px-5 py-3 text-sm font-bold text-white">
            未完成待办
            <span className="ml-3 rounded-full bg-red-500 px-3 py-1 text-white">{data.unread_count}</span>
          </div>
        }
      />

      <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
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
                <option key={value} value={value}>
                  {label}
                </option>
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
        </div>

        <div className="p-5">
          {error ? <ErrorState message={error} /> : null}
          {loading ? (
            <LoadingState label="正在加载待批阅任务…" />
          ) : data.records.length === 0 ? (
            <EmptyState title="暂无待批阅任务。" description="学生推送报告后，待办会展示在这里。" />
          ) : (
            <DataTable aria-label="导师待批阅任务">
              <thead>
                <DataTableRow className="hover:bg-transparent">
                  <DataTableHead>状态</DataTableHead>
                  <DataTableHead>学生</DataTableHead>
                  <DataTableHead>报告类型</DataTableHead>
                  <DataTableHead>报告编号</DataTableHead>
                  <DataTableHead>标题</DataTableHead>
                  <DataTableHead>提交时间</DataTableHead>
                  <DataTableHead className="text-center">操作</DataTableHead>
                </DataTableRow>
              </thead>
              <tbody>
                {data.records.map((record: SupervisorReviewQueueItem) => (
                  <DataTableRow key={record.todo_id}>
                    <DataTableCell className="font-semibold text-warning-600">
                      {statusLabels[record.todo_status]}
                    </DataTableCell>
                    <DataTableCell>{record.student_id}</DataTableCell>
                    <DataTableCell>{sourceLabels[record.source_type]}</DataTableCell>
                    <DataTableCell className="font-mono text-xs text-slate-500">{record.report_id}</DataTableCell>
                    <DataTableCell className="font-semibold text-slate-900">{record.title}</DataTableCell>
                    <DataTableCell className="tabular-nums">{formatDateTime(record.created_at)}</DataTableCell>
                    <DataTableCell className="text-center">
                      <Link
                        className={
                          record.todo_status === 'pending'
                            ? 'rounded bg-[#ff8a2a] px-3 py-2 text-xs font-bold text-white'
                            : 'text-sm font-semibold text-[#2f80ed]'
                        }
                        to={`/supervisor-review-queue/${record.submission_id}`}
                      >
                        {record.todo_status === 'pending' ? '批阅' : '查看记录'}
                      </Link>
                    </DataTableCell>
                  </DataTableRow>
                ))}
              </tbody>
            </DataTable>
          )}
        </div>
      </section>
    </div>
  );
}
