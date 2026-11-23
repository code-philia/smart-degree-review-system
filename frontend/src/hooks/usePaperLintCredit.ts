import {useCallback,useEffect,useRef,useState} from 'react';
import {fetchPaperLintCredit,type PaperLintCredit} from '../api/paperLint';

/** Account identity and balance are server-established; late responses cannot switch owners. */
export function usePaperLintCredit(ownerKey:string|null|undefined,active=false,refreshKey?:unknown){
  const [state,setState]=useState<{owner:string;credit:PaperLintCredit|null;error:boolean}|null>(null);
  const refreshRef=useRef<()=>Promise<void>>(async()=>{});
  const refresh=useCallback(()=>refreshRef.current(),[]);
  useEffect(()=>{
    if(!ownerKey){setState(null);refreshRef.current=async()=>{};return;}
    let disposed=false,inFlight:Promise<void>|null=null;
    let timer:ReturnType<typeof setTimeout>|undefined;
    function load():Promise<void>{
      if(disposed)return Promise.resolve();
      if(inFlight)return inFlight;
      clearTimeout(timer);
      inFlight=(async()=>{
        let failed=false;
        try{
          const credit=await fetchPaperLintCredit();
          if(disposed)return;
          if(credit.user_id!==ownerKey||credit.currency!=='CNY'||
            ![credit.granted_cny,credit.spent_cny,credit.reserved_cny,credit.available_cny].every(v=>typeof v==='string'&&/^\d+\.\d{9}$/.test(v))||
            !Number.isFinite(credit.remaining_percent)||credit.remaining_percent<0||credit.remaining_percent>100)throw new Error('Invalid credit response');
          setState({owner:ownerKey!,credit,error:false});
        }catch{
          failed=true;
          if(!disposed)setState(previous=>({owner:ownerKey!,credit:previous?.owner===ownerKey?previous.credit:null,error:true}));
        }finally{
          inFlight=null;
          if(!disposed)timer=setTimeout(()=>void load(),failed?30000:active?2000:15000);
        }
      })();
      return inFlight;
    }
    const focus=()=>void load();
    const visible=()=>{if(document.visibilityState==='visible')void load();};
    const storage=(event:StorageEvent)=>{if(!event.key||/^(paper-lint|numeric-review)-active-job:/.test(event.key))void load();};
    refreshRef.current=load;void load();
    window.addEventListener('focus',focus);window.addEventListener('storage',storage);document.addEventListener('visibilitychange',visible);
    return ()=>{disposed=true;clearTimeout(timer);window.removeEventListener('focus',focus);window.removeEventListener('storage',storage);
      document.removeEventListener('visibilitychange',visible);refreshRef.current=async()=>{};};
  },[ownerKey,active,refreshKey]);
  const current=state?.owner===ownerKey?state:null;
  return {credit:current?.credit??null,error:current?.error??false,refresh};
}
