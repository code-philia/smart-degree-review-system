import type { TranslationStatus as Status } from './reportTranslations';
export function TranslationStatus({status,error,retry}:{status:Status;error?:string;retry:()=>void}){
 if(status==='idle'||status==='ready')return null;
 return <div role="status" className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
  <span>{status==='pending'?'Translating report explanations into English…':error||'Some report text is not translated yet.'}</span>
  {status!=='pending'?<button type="button" className="font-medium text-brand-700 underline underline-offset-2" onClick={retry}>Retry translation</button>:null}
 </div>;
}
