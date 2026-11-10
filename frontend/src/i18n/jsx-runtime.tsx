// @ts-nocheck
// Normal JSX runtime adapter: native UI text is reactive; OriginalText boundaries protect source material.
import {jsx as originalJsx, jsxs as originalJsxs, Fragment} from 'react/jsx-runtime';
import {useSyncExternalStore,createContext,useContext} from 'react';
import {getLocale,getPresentationRevision,subscribe,translate,hasTranslation} from './locale.js';
export {Fragment};
export type { JSX } from 'react';
import type { ReactNode } from 'react';
type RichMessageProps={name:string;children?:ReactNode;count?:number;filteredCount?:number|null};
function emit(type,props,key){return (Array.isArray(props?.children)?originalJsxs:originalJsx)(type,props,key);}
const wrappers=new Map();
const componentWrappers=new WeakMap();
const textAttributes=['title','placeholder','aria-label','aria-valuetext','alt'];
export const OriginalTextContext=createContext(false);
export function preserveText(value){return emit(OriginalTextContext.Provider,{value:true,children:value});}
export function RichMessage({name,children,count,filteredCount}:RichMessageProps){
  useLanguage();
  if(getLocale()!=='en')return children;
  if(name==='sidebar-brand')return emit('span',{title:translate('智慧学位 AI 评阅辅助系统'),children:[emit('span',{className:'i18n-brand-line',children:'Smart Degree'},'name'),' ',emit('span',{className:'i18n-brand-line',children:'AI Review Assistant'},'purpose')]});
  if(name==='login-brand'||name==='login-card-brand')return [emit('span',{className:'i18n-brand-phrase',children:'Smart Degree'},'name'),emit('span',{className:'i18n-brand-separator',children:' · '},'separator'),emit('wbr',{},'break'),emit('span',{className:'i18n-brand-phrase',children:'AI Review Assistant'},'purpose')];
  if(name==='login-hint')return 'For SJTU students and staff';
  if(name==='login-description-rest')return translate('论文数据均在校内处理，保障信息安全。检测结果仅供参考，系统尚在测试中，欢迎通过“使用反馈”提出建议，我们将持续优化。');
  if(name==='wait-notice')return [emit('span',{className:'i18n-wait-title',children:'Your review is in progress,'},'title'),' ',emit('span',{className:'i18n-wait-note',children:'and we will email you when your report is ready.'},'note')];
  if(name==='pending-description')return [emit('span',{className:'i18n-pending-line',children:'Results update automatically.'},'updates'),' ',emit('span',{className:'i18n-pending-line',children:'You can view completed checks now.'},'completed')];
  if(name==='verification-filter')return emit('span',{title:'Verification warnings · '+translate('部分核验未完成，并不表示没有问题。数字表示警告条目数。'),'aria-label':translate(`规则未实现警告 ${count} 项`),children:`Unverified ${count}`});
  if(name==='history-total')return ['Total ',emit('span',{className:'font-medium text-slate-700',children:count},'total'),filteredCount==null?null:' · Matching ',filteredCount==null?null:emit('span',{className:'font-medium text-slate-700',children:filteredCount},'matching')];
  if(name==='history-selected')return [emit('span',{className:'font-semibold text-slate-900',children:count},'count'),` ${Number(count)===1?'report':'reports'} selected`];
  if(name==='page-jump'){const input=Array.isArray(children)?children.find(item=>item?.props?.inputMode==='numeric'):null;return input?['Go to page',input]:children;}
  if(name==='numeric-scope')return [emit('strong',{children:'About this check: '},'label'),'This check currently verifies only abstract claims and supporting evidence related to ',emit('strong',{children:'experimental data'},'evidence'),'.'];
  if(name==='numeric-missing')return ['No verifiable ',emit('strong',{children:'numerical claims'},'claims'),' were found in the abstract'];
  return children;
}
function useLanguage(){useSyncExternalStore(subscribe,getPresentationRevision,getPresentationRevision);}
function localizedPieces(value){
 if(!Array.isArray(value))return translate(value);
 const joined=value.join('');
 return hasTranslation(joined)?translate(joined):value.map(item=>typeof item==='string'?translate(item):item);
}
function Text({value}){useLanguage();const original=useContext(OriginalTextContext);return original?value:localizedPieces(value);}
function childrenText(children){
  if(typeof children==='string') return emit(Text,{value:children});
  if(Array.isArray(children)){
    const output=[];let run=[],start=0;
    const flush=()=>{if(run.length){output.push(emit(Text,{value:run.slice()},'text-'+start));run=[];}};
    children.forEach((item,i)=>{if(typeof item==='string'||typeof item==='number'){if(!run.length)start=i;run.push(item);}else{flush();output.push(item);}});flush();return output;
  }
  return children;
}
function attributes(props,original){
  const next={...props};
  const protectedKeys=new Set(String(props['data-i18n-original-attributes']||'').split(','));
  if(!original)for(const key of textAttributes)if(typeof next[key]==='string'&&!protectedKeys.has(key))next[key]=translate(next[key]);
  if(!original&&!protectedKeys.has('title')&&getLocale()==='en'&&typeof props.title==='string'&&/^规则未实现警告(?: \d+ 项)?$/.test(props.title))next.title=(props.title==='规则未实现警告'?'Verification warnings':translate(props.title))+' · '+translate('部分核验未完成，并不表示没有问题。数字表示警告条目数。');
  if(typeof props['aria-label']==='string'&&!next['data-ui-key'])next['data-ui-key']=props['aria-label'];
  return next;
}
function attributedComponent(type){
  if(componentWrappers.has(type))return componentWrappers.get(type);
  function Component(props){useLanguage();const original=useContext(OriginalTextContext);return emit(type,attributes(props,original));}
  Component.displayName='LocalizedAttributes';componentWrappers.set(type,Component);return Component;
}
function wrapper(tag){
  if(wrappers.has(tag))return wrappers.get(tag);
  function Native(props){
    useLanguage();const original=useContext(OriginalTextContext);
    const next=attributes(props,original);
    if(!original){
      if(typeof next.children==='string')next.children=translate(next.children);
      else if(Array.isArray(next.children)){
        if(next.children.every(v=>v==null||['string','number'].includes(typeof v)))next.children=localizedPieces(next.children);
        else next.children=next.children.map(v=>typeof v==='string'?translate(v):v);
      }
    }
    return emit(tag,next);
  }
  Native.displayName='LocalizedNative('+tag+')';wrappers.set(tag,Native);return Native;
}
function render(type,props,key){
  if(typeof type==='string') return emit(wrapper(type),props,key);
  if(props?.children!=null)props={...props,children:childrenText(props.children)};
  if((typeof type==='function'||typeof type==='object'&&type!==null)&&textAttributes.some(key=>typeof props?.[key]==='string'))return emit(attributedComponent(type),props,key);
  return emit(type,props,key);
}
export const jsx=render;
export const jsxs=render;
export const jsxDEV=render;
