import { useId, useState } from 'react';
import { Link } from 'react-router-dom';
import { Trash2 } from 'lucide-react';
import type { PaperLintReportListItem } from '../../api/paperLint';
import { formatChinaDateTime } from '../../utils/dateTime';
import { Button } from '../ui';

type ReportHistoryTableProps = {
  reports: PaperLintReportListItem[];
  historyPath: string;
  selectedReportIds: string[];
  onSelectionChange: (ids: string[]) => void;
  deleting: boolean;
  onDelete: (ids: string[], batch?: boolean) => void;
};

export function ReportHistoryTable({
  reports,
  historyPath,
  selectedReportIds,
  onSelectionChange,
  deleting,
  onDelete,
}: ReportHistoryTableProps) {
  const titleId = useId();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const pageCount = Math.max(1, Math.ceil(reports.length / pageSize));
  const currentPage = Math.min(page, pageCount);
  const pageStart = (currentPage - 1) * pageSize;
  const visibleReports = reports.slice(pageStart, pageStart + pageSize);
  const visibleIds = visibleReports.map(record => record.id);
  const selectedOnPage = visibleIds.filter(id => selectedReportIds.includes(id)).length;
  const allPageSelected = visibleIds.length > 0 && selectedOnPage === visibleIds.length;

  function selectPage(checked: boolean) {
    onSelectionChange(checked
      ? [...new Set([...selectedReportIds, ...visibleIds])]
      : selectedReportIds.filter(id => !visibleIds.includes(id)));
  }

  return (
    <section className="mb-6 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-5 py-4">
        <h2 id={titleId} className="font-semibold text-slate-900">PDF 论文检查报告</h2>
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-sm text-slate-500">共 {reports.length} 份报告</span>
          <Button
            size="sm"
            variant="danger"
            disabled={deleting || !selectedReportIds.length}
            onClick={() => onDelete(selectedReportIds, true)}
          >
            <Trash2 className="size-4" />删除选中（{selectedReportIds.length}）
          </Button>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table aria-labelledby={titleId} className="w-full min-w-[980px] text-left text-sm">
          <thead className="border-b border-slate-200 bg-slate-50 text-slate-600">
            <tr>
              <th scope="col" className="w-28 px-5 py-3 font-medium">
                <label className="flex items-center gap-2 whitespace-nowrap text-xs">
                  <input
                    type="checkbox"
                    aria-label="全选报告"
                    title="选择或取消选择本页全部报告"
                    className="size-4 accent-brand-600"
                    disabled={deleting}
                    checked={allPageSelected}
                    ref={element => { if (element) element.indeterminate = selectedOnPage > 0 && !allPageSelected; }}
                    onChange={event => selectPage(event.target.checked)}
                  />
                  全选本页
                </label>
              </th>
              <th scope="col" className="min-w-60 px-4 py-3 font-medium">文档名称</th>
              <th scope="col" className="whitespace-nowrap px-4 py-3 font-medium">检测类型</th>
              <th scope="col" className="whitespace-nowrap px-4 py-3 font-medium">检测结果</th>
              <th scope="col" className="whitespace-nowrap px-4 py-3 font-medium">报告生成时间</th>
              <th scope="col" className="whitespace-nowrap px-4 py-3 font-medium">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {visibleReports.map(record => (
              <tr key={record.id} className="text-slate-700 hover:bg-slate-50/70">
                <td className="px-5 py-3.5">
                  <input
                    type="checkbox"
                    aria-label={`选择报告：${record.source_filename}`}
                    className="size-4 accent-brand-600"
                    disabled={deleting}
                    checked={selectedReportIds.includes(record.id)}
                    onChange={event => onSelectionChange(event.target.checked
                      ? [...selectedReportIds, record.id]
                      : selectedReportIds.filter(id => id !== record.id))}
                  />
                </td>
                <td className="max-w-md break-words px-4 py-3.5 font-medium text-slate-900">{record.source_filename}</td>
                <td className="whitespace-nowrap px-4 py-3.5">规范性检测</td>
                <td className="whitespace-nowrap px-4 py-3.5">
                  <span className={record.summary.finding_count ? 'font-medium text-danger-600' : 'font-medium text-slate-700'}>
                    错误总数：{record.summary.finding_count}
                  </span>
                  {record.summary.error_rule_count || record.summary.unsupported_rule_count ? (
                    <p className="mt-1 text-xs text-amber-700">
                      {record.summary.error_rule_count ? '部分规则检测失败' : '部分规则无法判定'}
                    </p>
                  ) : null}
                </td>
                <td className="whitespace-nowrap px-4 py-3.5 tabular-nums text-slate-500">
                  {formatChinaDateTime(record.created_at, { includeSeconds: true })}
                </td>
                <td className="px-4 py-3.5">
                  <div className="flex items-center gap-2 whitespace-nowrap">
                    <Link className="rounded text-brand-700 underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-brand-500" to={`${historyPath}/pdf/${record.id}`}>
                      查看详情
                    </Link>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="px-2 text-danger-600"
                      disabled={deleting}
                      aria-label={`删除报告：${record.source_filename}`}
                      onClick={() => onDelete([record.id])}
                    >
                      <Trash2 className="size-3.5" />删除
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <nav aria-label="报告分页" className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 bg-white px-5 py-3 text-sm text-slate-500">
        <span>共 {reports.length} 条，显示第 {pageStart + 1}–{Math.min(pageStart + pageSize, reports.length)} 条</span>
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2">
            每页显示
            <select
              aria-label="每页显示条数"
              className="h-8 rounded-md border border-slate-300 bg-white px-2 text-slate-700 focus-visible:outline-2 focus-visible:outline-brand-500"
              value={pageSize}
              disabled={deleting}
              onChange={event => {
                setPageSize(Number(event.target.value));
                setPage(1);
              }}
            >
              {[10, 20, 50, 100].map(size => <option key={size} value={size}>{size}</option>)}
            </select>
            条
          </label>
          <Button size="sm" variant="secondary" disabled={deleting || currentPage === 1} onClick={() => setPage(currentPage - 1)}>上一页</Button>
          <span aria-live="polite" className="tabular-nums">第 {currentPage} / {pageCount} 页</span>
          <Button size="sm" variant="secondary" disabled={deleting || currentPage === pageCount} onClick={() => setPage(currentPage + 1)}>下一页</Button>
        </div>
      </nav>
    </section>
  );
}
