import { useSyncExternalStore, type ComponentProps } from 'react';
import { useTheme } from 'next-themes';
import { Check, CheckCircle2, Languages, Monitor, Moon, Settings2, Sun, X } from 'lucide-react';
import { getLocale, setLocale, subscribe } from '../i18n/locale';
import { preserveText } from '../i18n/jsx-runtime';
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogHeader, DialogTitle } from './shadcn/dialog';
import { Button } from './shadcn/button';

const appearances = [
  {value:'light', label:'浅色', Icon:Sun},
  {value:'dark', label:'深色', Icon:Moon},
  {value:'system', label:'跟随系统', Icon:Monitor},
] as const;

export function SettingsDialog({open,onOpenChange,onCloseAutoFocus}:{open:boolean;onOpenChange:(open:boolean)=>void;onCloseAutoFocus?:ComponentProps<typeof DialogContent>['onCloseAutoFocus']}) {
  const locale=useSyncExternalStore(subscribe,getLocale,getLocale);
  const {theme,setTheme}=useTheme();
  return <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogContent showCloseButton={false} onCloseAutoFocus={onCloseAutoFocus} className="preferences-dialog flex max-h-[calc(100dvh-2rem)] flex-col gap-0 overflow-hidden p-0 sm:max-w-[520px]">
      <DialogClose asChild><Button type="button" variant="ghost" size="icon-sm" className="absolute top-3 right-3" aria-label="关闭"><X size={16} aria-hidden="true"/></Button></DialogClose>
      <DialogHeader className="preferences-header">
        <span className="preferences-heading-icon" aria-hidden="true"><Settings2 size={21}/></span>
        <div><DialogTitle className="preferences-title">设置</DialogTitle>
          <DialogDescription className="preferences-description">界面偏好</DialogDescription></div>
      </DialogHeader>
      <div className="preferences-body">
        <section className="preferences-section" aria-labelledby="preferences-language-title">
          <div className="preferences-section-label"><Languages size={17} aria-hidden="true"/><h3 id="preferences-language-title">语言</h3></div>
          <div className="preferences-languages" role="group" aria-label="界面语言">
            <button type="button" lang="zh-CN" className="preference-language" aria-pressed={locale==='zh'} onClick={()=>setLocale('zh')}>
              <span>{preserveText('简体中文')}</span>{locale==='zh'?<Check size={17} aria-hidden="true"/>:<span className="preference-check-space"/>}
            </button>
            <button type="button" lang="en" className="preference-language" aria-pressed={locale==='en'} onClick={()=>setLocale('en')}>
              <span>{preserveText('English')}</span>{locale==='en'?<Check size={17} aria-hidden="true"/>:<span className="preference-check-space"/>}
            </button>
          </div>
        </section>
        <section className="preferences-section" aria-labelledby="preferences-appearance-title">
          <div className="preferences-section-label"><Sun size={17} aria-hidden="true"/><h3 id="preferences-appearance-title">外观</h3></div>
          <div className="preferences-appearances" role="group" aria-label="显示主题">
            {appearances.map(({value,label,Icon})=><button key={value} type="button" className="preference-appearance" aria-pressed={(theme??'light')===value} onClick={()=>setTheme(value)}>
              <span className="preference-swatch" data-appearance={value} aria-hidden="true"><span className="swatch-side"/><span className="swatch-top"/><span className="swatch-line"/><span className="swatch-card"/><span className="swatch-line short"/></span>
              <span className="preference-appearance-label"><Icon size={15} aria-hidden="true"/><span>{label}</span>{(theme??'light')===value?<Check size={15} className="preference-selected" aria-hidden="true"/>:null}</span>
            </button>)}
          </div>
        </section>
      </div>
      <div className="preferences-footer"><p><CheckCircle2 size={15} aria-hidden="true"/>自动保存</p><Button type="button" onClick={()=>onOpenChange(false)}>完成</Button></div>
    </DialogContent>
  </Dialog>;
}
