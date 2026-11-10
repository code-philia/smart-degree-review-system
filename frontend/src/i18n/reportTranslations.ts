import { useCallback, useEffect, useState, useSyncExternalStore } from 'react';
import apiClient from '../api';
import { addTranslations, clearTranslations, getLocale, hasTranslation, subscribe } from './locale';
export type TranslationResource={reportId?:string;jobId?:string};
export type TranslationResponse={locale:'en';status:'ready'|'partial'|'unavailable';translations:Record<string,string>;source_hash:string;model:'qwen';message?:string};
export type TranslationStatus='idle'|'pending'|TranslationResponse['status'];
let epoch=0;
const cache=new Map<string,{revision:string;response:TranslationResponse}>();
const pending=new Map<string,Promise<TranslationResponse|undefined>>();
const resourceTails=new Map<string,Promise<TranslationResponse|undefined>>();
const unavailable=(message?:string):TranslationResponse=>({locale:'en',status:'unavailable',translations:{},source_hash:'',model:'qwen',message});
const resourceKey=(resource:TranslationResource)=>resource.reportId?`reports/${encodeURIComponent(resource.reportId)}`:resource.jobId?`jobs/${encodeURIComponent(resource.jobId)}`:'';
function revisionKey(value:unknown){try{return JSON.stringify(value)??'';}catch{return String(value);}}
export function clearReportTranslations(){epoch++;cache.clear();pending.clear();resourceTails.clear();clearTranslations();}
export function assertTranslationsReady(texts:string[],locale='en'){
 if(locale==='en'&&texts.some(text=>!hasTranslation(text,'en')))throw new Error('Translation is not ready. Please retry before exporting.');
}
export async function ensureReportTranslations(resource:TranslationResource,revision?:unknown,options:{force?:boolean;locale?:string}={}):Promise<TranslationResponse|undefined>{
 if((options.locale??getLocale())!=='en')return undefined;
 const key=resourceKey(resource);if(!key)return undefined;
 const rev=revisionKey(revision),requestKey=`${key}:${rev}`,generation=epoch;
 const inFlight=pending.get(requestKey);if(inFlight)return inFlight;
 const saved=cache.get(key);if(!options.force&&saved?.revision===rev&&saved.response.status==='ready'){addTranslations(saved.response.translations);return saved.response;}
 // Serialize revisions of one resource, without repeated polling. A newer live/repair revision still gets its own request.
 if(pending.size>=32)return unavailable('Translation updates are waiting. Please retry shortly.');
 const prior=resourceTails.get(key);
 const request=(async()=>{
  if(prior)await prior.catch(()=>undefined);
  if(generation!==epoch)return undefined;
  try{
   let previousCoverage=0;
   let latest:TranslationResponse|undefined;
   // One logical flight may need several bounded backend batches. Continue only while coverage grows.
   for(let round=0;round<8;round++){
    if(generation!==epoch)return undefined;
    const {data}=await apiClient.post<TranslationResponse>(`/normative/paper-lint/${key}/translations`,{locale:'en'},{timeout:180000});
    if(generation!==epoch)return undefined;
    if(data?.locale!=='en'||!['ready','partial','unavailable'].includes(data.status)||!data.translations||typeof data.translations!=='object')throw new Error('Invalid translation response');
    addTranslations(data.translations);
    cache.delete(key);cache.set(key,{revision:rev,response:data});while(cache.size>16)cache.delete(cache.keys().next().value!);
    latest=data;
    const coverage=Object.keys(data.translations).length;
    if(data.status!=='partial'||coverage<=previousCoverage)return data;
    previousCoverage=coverage;
   }
   return latest;
  }catch{return generation===epoch?unavailable('English translation is temporarily unavailable. Your original report is unchanged.'):undefined;}
 })();
 pending.set(requestKey,request);
 resourceTails.set(key,request);
 void request.finally(()=>{
  if(pending.get(requestKey)===request)pending.delete(requestKey);
  if(resourceTails.get(key)===request)resourceTails.delete(key);
 });
 return request;
}
export function useReportTranslations(resource:TranslationResource,revision?:unknown){
 const locale=useSyncExternalStore(subscribe,getLocale,getLocale);
 const key=resourceKey(resource),rev=revisionKey(revision);
 const [attempt,setAttempt]=useState(0);
 const [state,setState]=useState<{key:string;rev:string;status:TranslationStatus;error?:string}>({key:'',rev:'',status:'idle'});
 useEffect(()=>{
  if(locale!=='en'||!key)return;
  let active=true;
  setState({key,rev,status:'pending'});
  const timer=setTimeout(()=>{void ensureReportTranslations(resource,revision,{force:attempt>0,locale:'en'}).then(response=>{
   if(active&&response)setState({key,rev,status:response.status,error:response.status==='ready'?undefined:'Some report text is not translated yet. You can retry or switch to Chinese.'});
  });},200);
  return()=>{active=false;clearTimeout(timer);};
 },[locale,key,rev,attempt]);
 const retry=useCallback(()=>setAttempt(n=>n+1),[]);
 return {status:locale!=='en'||!key?'idle' as const:state.key===key&&state.rev===rev?state.status:'pending' as const,error:state.error,retry};
}
