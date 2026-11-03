import { Select } from 'radix-ui';
import { Check, ChevronDown, ChevronLeft, ChevronRight } from 'lucide-react';

type Props = {
  total: number;
  page: number;
  pageCount: number;
  pageSize: number;
  disabled: boolean;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
};

function pageItems(page: number, count: number): (number | 'start-gap' | 'end-gap')[] {
  if (count <= 7) return Array.from({ length: count }, (_, index) => index + 1);
  const start = Math.max(2, Math.min(page - 1, count - 3));
  const end = Math.min(count - 1, Math.max(page + 1, 4));
  return [1,
    ...(start === 3 ? [2] : start > 3 ? ['start-gap' as const] : []),
    ...Array.from({ length: end - start + 1 }, (_, index) => start + index),
    ...(end === count - 2 ? [count - 1] : end < count - 2 ? ['end-gap' as const] : []),
    count];
}

const control = 'inline-flex h-8 shrink-0 items-center justify-center rounded-md border text-[13px] font-medium leading-5 tabular-nums outline-none transition-colors focus-visible:ring-2 focus-visible:ring-brand-500/25 focus-visible:ring-offset-2 disabled:cursor-not-allowed motion-reduce:transition-none';
const arrow = `${control} w-7 border-slate-200 bg-white text-slate-600 enabled:hover:border-brand-500 enabled:hover:bg-brand-50 enabled:hover:text-brand-600 disabled:border-slate-100 disabled:bg-slate-50 disabled:text-slate-300 sm:w-8`;

export function ReportPagination({ total, page, pageCount, pageSize, disabled, onPageChange, onPageSizeChange }: Props) {
  return <div className="grid w-full grid-cols-[1fr_auto] items-center gap-x-3 gap-y-3 [font-family:var(--font-app)] text-[13px] leading-5 lg:ml-auto lg:flex lg:w-auto">
    <span className="whitespace-nowrap text-slate-500">共 {total} 项</span>
    <div role="group" aria-label="报告页码" className="col-span-2 row-start-2 flex items-center justify-center gap-0.5 sm:gap-1">
      <button type="button" aria-label="上一页" title="上一页" className={arrow} disabled={disabled || page <= 1} onClick={() => onPageChange(page - 1)}>
        <ChevronLeft aria-hidden="true" className="size-3.5" />
      </button>
      {pageItems(page, pageCount).map(item => typeof item === 'number'
        ? <button key={item} type="button" aria-label={`第 ${item} 页`} aria-current={item === page ? 'page' : undefined} disabled={disabled} onClick={() => onPageChange(item)}
          className={`${control} min-w-6 px-1 sm:min-w-8 sm:px-2 ${item === page ? 'border-brand-500 bg-brand-50/60 text-brand-600' : 'border-transparent bg-white text-slate-600 enabled:hover:bg-slate-50 enabled:hover:text-brand-600'} disabled:opacity-50`}>{item}</button>
        : <span key={item} aria-hidden="true" className="flex h-8 w-5 shrink-0 items-center justify-center text-slate-400 sm:w-8">…</span>)}
      <button type="button" aria-label="下一页" title="下一页" className={arrow} disabled={disabled || page >= pageCount} onClick={() => onPageChange(page + 1)}>
        <ChevronRight aria-hidden="true" className="size-3.5" />
      </button>
    </div>
    <Select.Root value={String(pageSize)} onValueChange={value => onPageSizeChange(Number(value))} disabled={disabled}>
      <Select.Trigger aria-label="每页显示条数" className={`${control} group col-start-2 row-start-1 min-w-24 justify-between gap-2 border-slate-200 bg-white px-2.5 text-slate-600 hover:border-slate-300 data-[state=open]:border-brand-500 disabled:opacity-50`}>
        <Select.Value>{pageSize} / 页</Select.Value>
        <Select.Icon asChild><ChevronDown aria-hidden="true" className="size-3.5 text-slate-400 transition-transform group-data-[state=open]:rotate-180 motion-reduce:transition-none" /></Select.Icon>
      </Select.Trigger>
      <Select.Portal>
        <Select.Content position="popper" align="end" sideOffset={6} collisionPadding={8}
          className="z-50 min-w-28 overflow-hidden rounded-xl border border-slate-200 bg-white p-1 shadow-lg shadow-slate-900/10">
          <Select.Viewport>
            {[5, 10, 20, 50, 100].map(size => <Select.Item key={size} value={String(size)}
              className="flex h-8 cursor-pointer select-none items-center justify-between gap-3 rounded-lg px-2.5 text-[13px] leading-5 tabular-nums text-slate-600 outline-none data-[highlighted]:bg-slate-50 data-[state=checked]:bg-brand-50 data-[state=checked]:text-brand-600">
              <Select.ItemText>{size} / 页</Select.ItemText>
              <Select.ItemIndicator><Check aria-hidden="true" className="size-3.5" /></Select.ItemIndicator>
            </Select.Item>)}
          </Select.Viewport>
        </Select.Content>
      </Select.Portal>
    </Select.Root>
    <span aria-live="polite" className="sr-only">第 {page} / {pageCount} 页</span>
  </div>;
}
