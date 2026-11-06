import {Clock3,Mail} from 'lucide-react';
import type {PaperLintEta} from '../../api/paperLint';
import type {CompletionNotification} from '../../api/reportNotifications';

function etaLabel(eta?:PaperLintEta|null){
  if(eta?.status==='overdue')return '用时比预计稍长，请耐心等待';
  if(eta?.status!=='available'||!Number.isFinite(eta.max_seconds)||!Number.isFinite(eta.min_seconds))return '正在估算剩余时间';
  const minutes=Math.max(1,Math.ceil((eta.remaining_seconds??eta.max_seconds!)/60));
  return minutes===1?'预计 1 分钟内完成':`预计还需约 ${minutes} 分钟`;
}
export function DetectionWaitNotice({eta,notification}:{eta?:PaperLintEta|null;notification?:CompletionNotification|null}){
  const canEmail=notification?.delivery_available&&notification.email;
  return <div role="status" aria-live="polite" className="mb-5 border-b border-brand-100 pb-5">
    <div className="flex flex-wrap items-center justify-between gap-x-5 gap-y-3">
      <div className="flex items-center gap-2.5">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-xl border border-brand-100 bg-white text-brand-600"><Clock3 className="size-5" aria-hidden="true"/></span>
        <h2 className="text-lg font-semibold tracking-tight text-slate-900">系统正在检测中</h2>
      </div>
      <p className="rounded-lg border border-brand-100 bg-brand-50 px-3.5 py-2 text-base font-semibold tabular-nums text-brand-700 sm:text-lg">{etaLabel(eta)}</p>
    </div>
    <div className="mt-3 text-sm leading-7 text-slate-600">
      {canEmail?<p className="flex items-center gap-2 font-medium text-brand-800"><Mail className="size-4 shrink-0" aria-hidden="true"/><span>检测完成后将通过邮件通知您</span></p>
        :<p>检测完成后，报告将自动保存在历史报告中。</p>}
      <p>无需停留在此页面，后台检测将继续进行。</p>
      {canEmail?<p className="mt-1 break-all text-xs leading-5 text-slate-500">接收邮箱：<span>{notification.email}</span></p>
        :notification&&!notification.delivery_available?<span className="mt-1 inline-block rounded-md bg-slate-100 px-2 text-xs leading-6 text-slate-500">邮件通知暂未开通</span>:null}
      {eta?.status==='available'?<p className="mt-1 text-xs leading-5 text-slate-500">时间根据历史任务及当前排队情况估算，实际用时可能变化。</p>:null}
    </div>
  </div>;
}
