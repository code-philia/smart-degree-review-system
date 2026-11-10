import { RichMessage } from '../../i18n/jsx-runtime';
import {Clock3} from 'lucide-react';
import type {PaperLintEta} from '../../api/paperLint';

function etaLabel(eta?:PaperLintEta|null){
  const seconds=eta?.remaining_seconds??eta?.max_seconds;
  if(eta?.status!=='available'||!Number.isFinite(seconds))return '正在估算剩余时间';
  const minutes=Math.max(1,Math.ceil(seconds!/60));
  return minutes===1?'预计 1 分钟内完成':`预计还需约 ${minutes} 分钟`;
}
export function DetectionWaitNotice({eta}:{eta?:PaperLintEta|null}){
  return <div role="status" aria-live="polite" className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between lg:gap-5">
    <h2 className="min-w-0 text-base font-semibold leading-7 tracking-tight text-slate-900"><RichMessage name="wait-notice">系统正在检测中，检测完成后将通过邮件通知您</RichMessage></h2>
    <p className="inline-flex max-w-full shrink-0 items-center gap-2 self-start rounded-lg border border-brand-100 bg-brand-50/70 px-3 py-1.5 text-sm font-medium leading-6 tabular-nums text-brand-700">
      <Clock3 className="size-4 shrink-0" aria-hidden="true"/>{etaLabel(eta)}
    </p>
  </div>;
}
