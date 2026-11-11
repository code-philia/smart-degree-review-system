import { Info, RefreshCw } from 'lucide-react';
import { useState } from 'react';
import type { PaperLintDailyQuota } from '../../api/paperLint';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '../shadcn/tooltip';

type Props = {quota: PaperLintDailyQuota | null; unavailable?: boolean; onRetry?: () => void};
export function DailyQuotaHint({quota, unavailable, onRetry}: Props) {
  const [open, setOpen] = useState(false);
  if (quota && !quota.limited) return null;
  if (!quota) return unavailable ? <button type="button" onClick={onRetry}
    className="inline-flex items-center gap-1.5 whitespace-nowrap text-sm text-muted-foreground hover:text-foreground">
    <RefreshCw className="size-3.5" />更新可用次数
  </button> : null;
  const exhausted = quota.used >= quota.limit;
  const reserved = !exhausted && quota.remaining === 0;
  const label = exhausted ? '今日次数已用完' : reserved ? '可用次数已暂占' : `今日剩余 ${quota.remaining} / ${quota.limit} 次`;
  return <span data-daily-quota="" className={`inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap text-sm tabular-nums ${exhausted || reserved ? 'text-amber-700 dark:text-amber-300' : 'text-muted-foreground'}`}>
    <span role="status" aria-live="polite">{label}</span>
    <TooltipProvider delayDuration={200}><Tooltip open={open} onOpenChange={setOpen}>
      <TooltipTrigger asChild><button type="button" aria-label="检测额度说明" onClick={() => setOpen(value => !value)}
        className="inline-flex size-6 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
        <Info className="size-4" />
      </button></TooltipTrigger>
      <TooltipContent side="top" sideOffset={8} className="max-w-72 whitespace-normal px-3 py-2.5 text-sm leading-6">
        每日最多生成 3 份报告，北京时间 00:00 刷新。仅报告生成成功计次；失败或取消不计次。进行中的任务暂占次数，额度按提交日期计算。
      </TooltipContent>
    </Tooltip></TooltipProvider>
  </span>;
}
