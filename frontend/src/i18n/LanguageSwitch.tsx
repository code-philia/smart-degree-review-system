import { useSyncExternalStore } from 'react';
import { Languages } from 'lucide-react';
import { getLocale, setLocale, subscribe } from './locale';
export function LanguageSwitch({login=false}:{login?:boolean}) {
 const locale=useSyncExternalStore(subscribe,getLocale,getLocale);
 const controls=<div className="i18n-languages" role="group" aria-label="Language / 语言">
  <Languages size={15} aria-hidden="true" />
  <button type="button" lang="zh-CN" aria-pressed={locale==='zh'} onClick={()=>setLocale('zh')}>中文</button>
  <button type="button" lang="en" aria-pressed={locale==='en'} onClick={()=>setLocale('en')}>EN</button>
 </div>;
 return login?<div className="i18n-login-language">{controls}</div>:controls;
}
