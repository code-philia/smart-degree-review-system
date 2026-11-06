import {useEffect,useState,type FormEvent} from 'react';
import {Mail} from 'lucide-react';
import {fetchCompletionNotification,saveCompletionEmail,type CompletionNotification} from '../../api/reportNotifications';

export function CompletionEmailSettings({userId,busy,onChange}:{userId:string;busy:boolean;onChange:(value:CompletionNotification)=>void}){
  const [settings,setSettings]=useState<CompletionNotification|null>(null);
  const [email,setEmail]=useState('');const [saving,setSaving]=useState(false);const [error,setError]=useState('');
  useEffect(()=>{let active=true;void fetchCompletionNotification().then(value=>{if(active){setSettings(value);onChange(value);}}).catch(()=>{});return()=>{active=false;};},[userId,onChange]);
  async function save(event:FormEvent){event.preventDefault();setSaving(true);setError('');try{const value=await saveCompletionEmail(email);setSettings(value);onChange(value);}catch{setError('邮箱保存失败，请确认地址后重试。');}finally{setSaving(false);}}
  if(!settings)return null;
  return <div className="border-t border-slate-100 px-[18px] py-3 sm:px-6" aria-label="检测完成通知">
    <div className="flex items-start gap-2.5 text-xs leading-6 text-slate-500"><Mail className="mt-1 size-4 shrink-0 text-brand-500" aria-hidden="true"/>
      <div className="min-w-0"><span className="font-medium text-slate-700">完成通知</span>
        {settings.email?<span className="ml-2 break-all">{settings.email}</span>:<span className="ml-2">{settings.fixed?'当前账号暂无可用通知邮箱，请联系管理员。':'补充邮箱，检测完成后接收报告通知'}</span>}
        {!settings.delivery_available?<span className="ml-2 inline-block rounded bg-slate-100 px-1.5 text-[11px] text-slate-500">邮件通知暂未开通</span>:null}
      </div>
    </div>
    {!settings.fixed&&!settings.email?<form onSubmit={save} className="mt-2 flex flex-wrap items-center gap-2">
      <input aria-label="接收通知邮箱" type="email" required maxLength={254} value={email} onChange={event=>setEmail(event.target.value)} disabled={busy||saving}
        placeholder="输入接收邮箱" className="min-w-0 flex-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100"/>
      <button type="submit" disabled={busy||saving} className="rounded-lg bg-brand-50 px-3 py-2 text-sm font-medium text-brand-700 hover:bg-brand-100 disabled:opacity-50">{saving?'保存中…':'保存邮箱'}</button>
      {error?<p role="alert" className="w-full text-xs text-red-600">{error}</p>:null}
    </form>:null}
  </div>;
}
