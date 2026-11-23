/** @jsxImportSource react */
import {useSyncExternalStore} from 'react';
import {Zap,Wallet,ChevronDown} from 'lucide-react';
import {Popover,PopoverTrigger,PopoverContent} from '../shadcn/popover';
import {getLocale,subscribe,translateStatic} from '../../i18n/locale';
import type {PaperLintCredit} from '../../api/paperLint';
import policy from '../../../../shared/paper-lint-credit-policy.json';
import './paper-lint-credit.css';

const estimates:Record<string,string>=policy.estimated_cny;
function useEnglish(){return useSyncExternalStore(subscribe,getLocale,getLocale)==='en';}
const amount=(value:string)=>Number(value).toFixed(2);
export const hasPaidSelection=(ids:string[])=>ids.some(id=>Object.prototype.hasOwnProperty.call(estimates,id));
export function creditAllowsRules(credit:PaperLintCredit|null|undefined,ids:string[],unavailable=false){
  return !hasPaidSelection(ids)||Boolean(credit&&!unavailable&&Number(credit.available_cny)>0);
}
export function isCreditInsufficient(credit:PaperLintCredit|null|undefined,ids:string[],unavailable=false){
  return Boolean(credit&&!unavailable&&hasPaidSelection(ids)&&Number(credit.available_cny)<=0);
}
export function CreditInsufficientNotice({id}:{id:string}){
  const en=useEnglish();
  return <div id={id} className="credit-insufficient-notice" role="status">
    <Wallet size={16} strokeWidth={1.8} aria-hidden="true"/>
    <div><strong>{en?'Insufficient credit':'额度不足'}</strong>
      <p>{en?'Deselect checks that use credit to continue with free checks.':'取消需要额度的规则后，仍可使用免费规则进行检测。'}</p>
    </div>
  </div>;
}
function CreditRing({percent}:{percent:number}){
  const value=Math.max(0,Math.min(100,percent));
  return <svg className="credit-balance-ring" viewBox="0 0 36 36" aria-hidden="true" focusable="false">
    <circle className="credit-ring-track" cx="18" cy="18" r="14.5"/>
    {value>0?<circle className="credit-ring-progress" cx="18" cy="18" r="14.5" pathLength="100" strokeDasharray="100" strokeDashoffset={100-value}/>:null}
  </svg>;
}
type BalanceProps={credit:PaperLintCredit|null;unavailable?:boolean;onRetry?:()=>void};
export function CreditBalance({credit,unavailable=false,onRetry}:BalanceProps){
  const en=useEnglish();
  const available=credit?amount(credit.available_cny):'—';
  const label=en?'Available credit':'可用额度';
  const control=<button type="button" className="credit-balance" disabled={!credit&&!unavailable}
    aria-label={credit?(en?`Available credit: ${available} yuan. View details`:`可用额度 ${available} 元，查看额度说明`):(en?'Update available credit':'更新可用额度')}
    onClick={!credit?onRetry:undefined}>
    <CreditRing percent={credit?.remaining_percent??0}/>
    <span className="credit-balance-copy"><span>{label}</span><strong title={credit?.available_cny}>{credit?<><span className="credit-currency">¥</span>{available}</>:available}</strong></span>
    <ChevronDown size={14} strokeWidth={1.6} aria-hidden="true"/>
  </button>;
  if(!credit)return control;
  const percent=Number(credit.remaining_percent.toFixed(1));
  return <Popover><PopoverTrigger asChild>{control}</PopoverTrigger><PopoverContent align="end" className="credit-popover">
    <div className="credit-popover-title"><Wallet size={16} strokeWidth={1.7} aria-hidden="true"/>{en?'Review credit':'检测额度'}</div>
    <dl>
      <div><dt>{en?'Account allowance':'账号总额度'}</dt><dd title={credit.granted_cny}>¥{amount(credit.granted_cny)}</dd></div>
      <div><dt>{en?'Used':'已使用'}</dt><dd title={credit.spent_cny}>¥{amount(credit.spent_cny)}</dd></div>
      {Number(credit.reserved_cny)>0?<div><dt>{en?'Reserved':'预占额度'}</dt><dd title={credit.reserved_cny}>¥{amount(credit.reserved_cny)}</dd></div>:null}
      <div><dt>{en?`Available (${percent}%)`:`当前可用（${percent}%）`}</dt><dd title={credit.available_cny}>¥{available}</dd></div>
    </dl>
    <div className="credit-detail-track" aria-hidden="true"><span style={{width:`${percent}%`}}/></div>
    <p>{en?'Only model-based checks use credit. Charges follow actual token usage.':'仅模型检测消耗额度，按实际 token 用量结算。'}</p>
    {unavailable?<button type="button" className="credit-retry" onClick={onRetry}>{en?'Update credit':'更新额度'}</button>:null}
  </PopoverContent></Popover>;
}
export function CreditPrice({ruleId}:{ruleId:string}){
  const en=useEnglish(),price=estimates[ruleId];
  if(!price)return null;
  return <span className="credit-rule-price" title={en?'Estimated cost per paper, based on real-paper tests. Actual token usage determines the final charge.':'真实论文实测预估费用，按每篇展示；最终按实际 token 用量结算。'}>
    <Zap size={14} fill="currentColor" strokeWidth={1.3} aria-hidden="true"/><span>{en?'Est. ':'约 '}¥{price}</span>
  </span>;
}
export function CreditEstimate({selectedRuleIds}:{selectedRuleIds:string[]}){
  const en=useEnglish();
  const total=selectedRuleIds.reduce((sum,id)=>sum+Math.round(Number(estimates[id]||0)*100),0)/100;
  return <div className="credit-estimate" aria-live="polite"><span className="credit-estimate-main"><span>{en?'Estimated total':'本次预计'}</span><strong>¥{total.toFixed(2)}</strong></span>
    <span className="credit-estimate-note">{en?'Billed by actual usage':'按实际用量结算'}</span></div>;
}
export function CreditAbout(){
  const en=useEnglish();
  const zh='聚焦公式引用、文献引用目录页码及语言规范等可定位问题。上传论文后，您可自主选择已开放规则，逐项查看检测结果，并联动定位到论文原文位置。受算力资源限制，每位用户初始检测额度为 ¥100，请提前确认论文版本、合理勾选检测规则。检测结果仅供参考，系统尚在测试中，欢迎通过“使用反馈”提出建议。';
  return <p>{en?translateStatic(zh,'en'):zh}</p>;
}
