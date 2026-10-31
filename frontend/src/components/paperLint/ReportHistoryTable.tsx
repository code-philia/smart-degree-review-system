import { useId, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowUpRight, Check, FileText, ListChecks, MoreHorizontal, Search, Trash2, X } from 'lucide-react';
import type { PaperLintReportListItem } from '../../api/paperLint';
import { formatChinaDateTime } from '../../utils/dateTime';
import { Button } from '../ui';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '../shadcn/dropdown-menu';

const actionMenuClassName = 'w-40 rounded-xl border border-slate-200 bg-white p-1.5 text-slate-700 shadow-xl ring-0 duration-200 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:slide-in-from-top-2 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:slide-out-to-top-2 motion-reduce:animate-none!';

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
      <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-5">
        <div className="flex flex-wrap items-center gap-3">
          <h2 id={titleId} className="text-base font-semibold tracking-tight text-slate-900">PDF 论文检查报告</h2>
          <span className="rounded-md bg-slate-100 px-2 py-1 text-[13px] tabular-nums text-slate-500">{reports.length} 份</span>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild ref={managementTriggerRef}>
            <Button size="sm" variant="ghost" aria-label="报告管理" title="报告管理" disabled={deleting} className="size-9 rounded-xl border border-slate-200/80 p-0">
              <MoreHorizontal className="size-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className={actionMenuClassName}>
            <DropdownMenuItem disabled={deleting} onSelect={() => setManaging(true)} className="cursor-pointer gap-2 rounded-lg px-3 py-2.5 focus:bg-slate-100 focus:text-slate-900">
              <ListChecks />批量管理
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      <div className="flex flex-wrap items-center gap-3 border-t border-slate-100 bg-slate-50/40 px-6 py-4">
        <div className="relative w-full sm:max-w-[400px]">
          <Search aria-hidden="true" className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
          <input
            ref={searchInputRef}
            type="search"
            aria-label="搜索检测报告"
            placeholder="搜索文档名称…"
            value={query}
            disabled={deleting}
            onChange={event => changeQuery(event.target.value)}
            className="h-11 w-full rounded-xl border border-slate-200 bg-white pl-10 pr-11 text-sm text-slate-800 shadow-sm shadow-slate-100/50 outline-none transition-[border-color,box-shadow] placeholder:text-slate-400 focus:border-brand-300 focus:ring-4 focus:ring-brand-50 disabled:opacity-60 motion-reduce:transition-none [&::-webkit-search-cancel-button]:appearance-none"
          />
          {query ? (
            <button type="button" aria-label="清空搜索" title="清空搜索" disabled={deleting} onClick={clearSearch}
              className="absolute right-1.5 top-1/2 flex size-8 -translate-y-1/2 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700 focus-visible:outline-2 focus-visible:outline-brand-500 disabled:opacity-60 motion-reduce:transition-none">
              <X aria-hidden="true" className="size-4" />
            </button>
          ) : null}
        </div>
        {filtering ? <span role="status" className="text-[13px] tabular-nums text-slate-500">匹配 {filteredReports.length} 份</span> : null}
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
        <table aria-labelledby={titleId} className="w-full min-w-[840px] table-fixed text-left text-sm">
          <thead className="border-y border-slate-100 bg-slate-50/70 text-[13px] text-slate-500">
            <tr>
              {managing ? <th scope="col" className="w-12 pl-6 pr-2 py-3 font-medium">
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
              <th scope="col" className="px-6 py-3 font-medium">文档名称</th>
              <th scope="col" className="w-[124px] px-4 py-3 font-medium">检测类型</th>
              <th scope="col" className="w-[156px] px-4 py-3 font-medium">检测结果</th>
              <th scope="col" className="w-[156px] px-4 py-3 font-medium">报告生成时间</th>
              <th scope="col" className="w-[152px] px-4 py-3 font-medium">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {visibleReports.map(record => (
              <tr key={record.id} className="bg-white text-slate-700 transition-colors duration-150 even:bg-slate-50/60 hover:bg-brand-50/40 motion-reduce:transition-none">
                {managing ? <td className="animate-in pl-6 pr-2 py-6 fade-in-0 motion-reduce:animate-none">
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
                <td className="px-6 py-6">
                  <div className="flex items-center gap-3">
                    <span className="flex h-10 w-9 shrink-0 items-center justify-center rounded-xl border border-slate-200/80 bg-slate-50 text-slate-400"><FileText className="size-[18px]" aria-hidden="true" /></span>
                    <span title={record.source_filename} className="line-clamp-2 break-all text-sm font-medium leading-6 text-slate-800">{record.source_filename}</span>
                  </div>
                </td>
                <td className="px-4 py-6"><span className="whitespace-nowrap text-[13px] text-slate-500">规范性检测</span></td>
                <td className="px-4 py-6">
                  <span className="inline-flex whitespace-nowrap rounded-md border border-slate-200/80 bg-slate-100/60 px-2 py-1 text-[13px] tabular-nums text-slate-700">
                    错误总数：{record.summary.finding_count}
                  </span>
                  {record.summary.error_rule_count || record.summary.unsupported_rule_count ? (
                    <p className="mt-1.5 text-[13px] text-amber-700">
                      {record.summary.error_rule_count ? '部分规则检测失败' : '部分规则无法判定'}
                    </p>
                  ) : null}
                </td>
                <td className="px-4 py-6">
                  <time dateTime={record.created_at} className="block whitespace-pre-line text-[13px] leading-6 tabular-nums text-slate-500">
                    {formatChinaDateTime(record.created_at, { includeSeconds: true }).replace(' ', '\n')}
                  </time>
                </td>
                <td className="px-4 py-6">
                  <div className="flex items-center gap-1 whitespace-nowrap">
                    <Link className="group inline-flex h-8 items-center gap-1 rounded-lg px-1.5 text-[13px] font-medium text-brand-700 transition-colors hover:bg-brand-50 hover:text-brand-800 focus-visible:outline-2 focus-visible:outline-brand-500 motion-reduce:transition-none" to={`${historyPath}/pdf/${record.id}`}>
                      查看详情<ArrowUpRight className="size-3.5 transition-transform group-hover:-translate-y-px group-hover:translate-x-px motion-reduce:transform-none" aria-hidden="true" />
                    </Link>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button size="sm" variant="ghost" className="size-8 shrink-0 rounded-lg p-0 text-slate-400" disabled={deleting} aria-label={`更多操作：${record.source_filename}`} title="更多操作"><MoreHorizontal className="size-4" /></Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" className={actionMenuClassName}>
                        <DropdownMenuItem disabled={deleting} onSelect={() => onDelete([record.id])} className="cursor-pointer gap-2 rounded-lg px-3 py-2.5 text-danger-600 focus:bg-red-50 focus:text-danger-600"><Trash2 />删除报告</DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                </td>
              </tr>
            ))}
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
