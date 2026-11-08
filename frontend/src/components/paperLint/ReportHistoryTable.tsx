import { useId, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowUpRight, RotateCw, Check, ListChecks, Search, Trash2, X } from 'lucide-react';
import type { PaperLintReportListItem } from '../../api/paperLint';
import { formatChinaDateTime } from '../../utils/dateTime';
import { Button } from '../ui';

const rowActionClassName = 'inline-flex h-9 shrink-0 items-center justify-center gap-1.5 rounded-lg border px-2 text-sm font-normal leading-6 transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-50 motion-reduce:transition-none';


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
  const managementTriggerRef = useRef<HTMLButtonElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(5);
  const [managing, setManaging] = useState(false);
  const normalizedQuery = query.trim().toLowerCase();
  const filtering = normalizedQuery.length > 0;
  const filteredReports = filtering
    ? reports.filter(record => record.source_filename.toLowerCase().includes(normalizedQuery))
    : reports;
  const pageCount = Math.max(1, Math.ceil(filteredReports.length / pageSize));
  const currentPage = Math.min(page, pageCount);
  const pageStart = (currentPage - 1) * pageSize;
  const visibleReports = filteredReports.slice(pageStart, pageStart + pageSize);
  const visibleIds = visibleReports.map(record => record.id);
  const selectedOnPage = visibleIds.filter(id => selectedReportIds.includes(id)).length;
  const allPageSelected = visibleIds.length > 0 && selectedOnPage === visibleIds.length;

  function changeQuery(value: string) {
    setQuery(value);
    setPage(1);
    onSelectionChange([]);
  }

  function clearSearch() {
    changeQuery('');
    searchInputRef.current?.focus();
  }

  function selectPage(checked: boolean) {
    onSelectionChange(checked
      ? [...new Set([...selectedReportIds, ...visibleIds])]
      : selectedReportIds.filter(id => !visibleIds.includes(id)));
  }

  function finishManaging() {
    setManaging(false);
    onSelectionChange([]);
    managementTriggerRef.current?.focus();
  }

  return (
    <section className="mb-6 overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-[0_8px_32px_-24px_rgba(15,23,42,0.25)]">
      <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4 px-6 py-5 lg:grid-cols-[minmax(0,1fr)_minmax(240px,320px)_auto]">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <h2 id={titleId} className="text-base font-semibold tracking-tight text-slate-900">规范性检测报告</h2>
          {filtering ? <span role="status" className="text-[13px] font-medium tabular-nums text-brand-700">匹配 {filteredReports.length} 份</span> : null}
        </div>
        <div className="relative order-last col-span-2 w-full lg:order-none lg:col-span-1">
          <Search aria-hidden="true" className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
          <input
            ref={searchInputRef}
            type="search"
            aria-label="搜索检测报告"
            placeholder="搜索文档名称…"
            value={query}
            disabled={deleting}
            onChange={event => changeQuery(event.target.value)}
            className="h-10 w-full rounded-lg border border-slate-200 bg-slate-50/60 pl-10 pr-11 text-sm text-slate-800 outline-none transition-[border-color,box-shadow] placeholder:text-slate-400 focus:border-brand-300 focus:bg-white focus:ring-4 focus:ring-brand-50 disabled:opacity-60 motion-reduce:transition-none [&::-webkit-search-cancel-button]:appearance-none"
          />
          {query ? (
            <button type="button" aria-label="清空搜索" title="清空搜索" disabled={deleting} onClick={clearSearch}
              className="absolute right-1.5 top-1/2 flex size-8 -translate-y-1/2 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700 focus-visible:outline-2 focus-visible:outline-brand-500 disabled:opacity-60 motion-reduce:transition-none">
              <X aria-hidden="true" className="size-4" />
            </button>
          ) : null}
        </div>
        <button
          ref={managementTriggerRef}
          type="button"
          disabled={deleting}
          aria-expanded={managing}
          onClick={() => managing ? finishManaging() : setManaging(true)}
          className="inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 transition-colors hover:border-slate-300 hover:bg-slate-50 aria-expanded:border-brand-200 aria-expanded:bg-brand-50 aria-expanded:text-brand-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500 disabled:cursor-not-allowed disabled:opacity-50 motion-reduce:transition-none"
        >
          <ListChecks aria-hidden="true" className="size-4" />批量管理
        </button>
      </div>
      {managing ? (
        <div role="region" aria-label="批量管理" className="mx-5 mb-4 mt-4 flex animate-in flex-wrap items-center justify-between gap-3 rounded-xl border border-brand-100 bg-brand-50/60 px-4 py-3 duration-200 fade-in-0 slide-in-from-top-2 motion-reduce:animate-none">
          <p className="text-sm text-slate-600" aria-live="polite">已选择 <span className="font-semibold text-slate-900">{selectedReportIds.length}</span> 份报告</p>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="ghost" disabled={deleting} onClick={finishManaging}><Check className="size-3.5" />完成管理</Button>
            <Button size="sm" variant="danger" disabled={deleting || !selectedReportIds.length} onClick={() => onDelete(selectedReportIds, true)}>
              <Trash2 className="size-3.5" />删除选中（{selectedReportIds.length}）
            </Button>
          </div>
        </div>
      ) : null}
      <div className="overflow-x-auto">
        <table aria-labelledby={titleId} className="w-full min-w-[960px] table-fixed text-left text-sm">
          <thead className="border-y border-slate-200/80 bg-slate-50 text-[13px] text-slate-700">
            <tr>
              {managing ? <th scope="col" className="w-12 pl-6 pr-2 py-3.5 font-semibold">
                <label className="flex items-center">
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
                  <span className="sr-only">全选本页</span>
                </label>
              </th> : null}
              <th scope="col" className="px-6 py-3.5 font-semibold">文档名称</th>
              <th scope="col" className="w-[108px] px-3 py-3.5 font-semibold">检测类型</th>
              <th scope="col" className="w-[144px] px-3 py-3.5 font-semibold">检测结果</th>
              <th scope="col" className="w-[144px] px-3 py-3.5 font-semibold">报告生成时间</th>
              <th scope="col" className="w-[328px] px-3 py-3.5 font-semibold">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200/80">
            {visibleReports.map(record => {
              const detailPath = `${historyPath}/pdf/${encodeURIComponent(record.id)}`;
              const incomplete = Boolean(record.summary.error_rule_count || record.summary.unsupported_rule_count);
              const resultTone = record.summary.finding_count > 0 || incomplete
                ? 'border-amber-200 bg-amber-50 text-amber-900'
                : 'border-emerald-200 bg-emerald-50 text-emerald-800';
              return (
              <tr key={record.id} className="bg-white text-sm font-normal leading-6 text-slate-700 transition-colors duration-150 even:bg-slate-50/40 hover:bg-brand-50/40 motion-reduce:transition-none">
                {managing ? <td className="animate-in pl-6 pr-2 py-4 fade-in-0 motion-reduce:animate-none">
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
                </td> : null}
                <td className="px-6 py-4">
                  <Link to={detailPath} title={record.source_filename} className="block truncate rounded-sm text-sm font-normal leading-6 text-slate-900 transition-colors hover:text-brand-700 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-brand-500 motion-reduce:transition-none">{record.source_filename}</Link>
                </td>
                <td className="px-3 py-4"><span className="whitespace-nowrap text-sm font-normal leading-6 text-slate-600">规范性检测</span></td>
                <td className="px-3 py-4">
                  <span className={`inline-flex whitespace-nowrap rounded-md border px-2 py-1 text-sm font-normal leading-6 tabular-nums ${resultTone}`}>
                    错误总数：{record.summary.finding_count}
                  </span>
                  {incomplete ? (
                    <p className="mt-1.5 text-sm font-normal leading-6 text-amber-700">
                      {record.summary.error_rule_count ? '部分规则检测失败' : '部分规则无法判定'}
                    </p>
                  ) : null}
                </td>
                <td className="px-3 py-4">
                  <time dateTime={record.created_at} className="block whitespace-pre-line text-sm font-normal leading-6 tabular-nums text-slate-600">
                    {formatChinaDateTime(record.created_at, { includeSeconds: true }).replace(' ', '\n')}
                  </time>
                </td>
                <td className="px-3 py-4">
                  <div className="flex items-center gap-2 whitespace-nowrap">
                    <Link className={`${rowActionClassName} group border-brand-100 bg-brand-50/70 text-brand-700 hover:border-brand-200 hover:bg-brand-100/70 hover:text-brand-800 focus-visible:outline-brand-500`} to={detailPath}>
                      查看详情<ArrowUpRight className="size-3.5 transition-transform group-hover:-translate-y-px group-hover:translate-x-px motion-reduce:transform-none" aria-hidden="true" />
                    </Link>
                    <Link to={`${detailPath}?rerun=1`}
                      aria-disabled={deleting || undefined}
                      tabIndex={deleting ? -1 : undefined}
                      onClick={event => { if (deleting) event.preventDefault(); }}
                      className={`${rowActionClassName} border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:bg-slate-50 hover:text-slate-900 focus-visible:outline-brand-500 aria-disabled:pointer-events-none aria-disabled:opacity-50`}>
                      <RotateCw aria-hidden="true" className="size-3.5" />增量补跑
                    </Link>
                    <button type="button" disabled={deleting} onClick={() => onDelete([record.id])}
                      className={`${rowActionClassName} border-red-100 bg-white text-danger-600 hover:border-red-200 hover:bg-red-50 focus-visible:outline-danger-600`}>
                      <Trash2 aria-hidden="true" className="size-3.5" />删除报告
                    </button>
                  </div>
                </td>
              </tr>
              );
            })}
            {!visibleReports.length ? (
              <tr>
                <td colSpan={managing ? 6 : 5} className="px-6 py-14 text-center">
                  <Search aria-hidden="true" className="mx-auto mb-3 size-6 text-slate-300" />
                  <p className="text-sm font-medium text-slate-700">{filtering ? '未找到匹配的报告' : '暂无检测报告'}</p>
                  {filtering ? <>
                    <p className="mt-2 text-[13px] text-slate-500">请尝试其他文档名称，或查看全部已保存报告。</p>
                    <Button size="sm" variant="ghost" disabled={deleting} onClick={clearSearch} className="mt-4 text-brand-700">查看全部报告</Button>
                  </> : null}
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
      <nav aria-label="报告分页" className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 bg-white px-6 py-4 text-[13px] text-slate-500">
        <span>共 {reports.length} 条，{filtering ? `匹配 ${filteredReports.length} 条，` : ''}显示第 {filteredReports.length ? pageStart + 1 : 0}–{Math.min(pageStart + pageSize, filteredReports.length)} 条</span>
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
              {[5, 10, 20, 50, 100].map(size => <option key={size} value={size}>{size}</option>)}
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
