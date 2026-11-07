const { all } = require('../database/db_runtime');
const MODEL_RULES = new Set(['typo_detection_check','bilingual_abstract_consistency_check',
  'bilingual_keywords_correspondence_check','abstract_numeric_consistency_check','sjtu_rule_32']);
function ids(row) {try {return JSON.parse(row.selected_rule_ids_json).filter(id=>typeof id==='string').sort();}catch{return [];}}
function profile(rules) {return rules.filter(id=>MODEL_RULES.has(id)).join(',');}

async function estimateJobEta(job, now=Date.now()) {
  if (!['pending','running'].includes(job.status) || job.cancelled_at) return null;
  const history = await all(`SELECT selected_rule_ids_json,created_at,started_at,updated_at FROM paper_lint_jobs
    WHERE status='completed' AND cancelled_at IS NULL AND attempts<=1 ORDER BY updated_at DESC LIMIT 100`);
  function range(row) {
    const selected=ids(row),key=selected.join(',');
    const usable=history.map(sample=>({sample,rules:ids(sample),seconds:(Date.parse(sample.updated_at)-Date.parse(sample.started_at||sample.created_at))/1000}))
      .filter(sample=>Number.isFinite(sample.seconds)&&sample.seconds>=2&&sample.seconds<=21_600);
    let comparable=usable.filter(sample=>sample.rules.join(',')===key);
    if(comparable.length<3) comparable=usable.filter(sample=>profile(sample.rules)===profile(selected)
      &&Math.abs(sample.rules.length-selected.length)<=Math.max(2,selected.length/2));
    if(comparable.length<3)return null;
    const durations=comparable.map(sample=>sample.seconds).sort((a,b)=>a-b);
    return {min:Math.floor(durations[Math.floor((durations.length-1)*.25)]*.8),
      max:Math.ceil(durations[Math.ceil(durations.length*.75)-1]*1.25),samples:durations.length,durations};
  }
  function point(estimate,spent){
    const remaining=estimate.durations.filter(duration=>duration>spent);
    return Math.max(0,remaining.length?remaining[Math.floor(remaining.length/2)]-spent:estimate.max-spent);
  }
  function timing(row){
    const estimate=range(row);
    const started=Date.parse(row.started_at||row.created_at);
    const elapsed=row.status==='running'&&Number.isFinite(started)?Math.max(0,(now-started)/1000):0;
    const selected=ids(row);
    let completed=[];
    try {completed=[...new Set(JSON.parse(row.progress_json)?.completed_rule_ids||[])].filter(id=>selected.includes(id));}catch{}
    if(row.status!=='running')completed=[];
    const updated=Date.parse(row.updated_at);
    const idle=completed.length&&Number.isFinite(updated)?Math.max(0,(now-Math.max(Number.isFinite(started)?started:updated,updated))/1000):elapsed;
    const pending=selected.filter(id=>!completed.includes(id));
    const residual=completed.length&&pending.length?range({selected_rule_ids_json:JSON.stringify(pending)}):null;
    const samples=Math.max(estimate?.samples||0,residual?.samples||0);
    if(!estimate&&!completed.length)return null;
    const historical=estimate?point(estimate,elapsed):0;
    const measured=completed.length&&pending.length?elapsed*pending.length/completed.length:0;
    const remainder=residual?point(residual,idle):measured;
    // Extend the estimate from current work rate and time since progress when
    // execution outlasts history, rather than freezing or stopping the ETA.
    const tail=Math.max(30,(estimate?.durations[Math.floor(estimate.durations.length/2)]||0)*.25,idle*.5);
    const saving=selected.length>0&&completed.length===selected.length;
    const remaining=saving?Math.max(15,idle*.5):historical>0
      ? completed.length&&remainder>0?(historical+remainder)/2:historical
      :Math.max(remainder,measured,tail);
    return {remaining:Math.max(1,remaining),min:Math.min(Math.max(0,(estimate?.min||0)-elapsed),remaining*.8),
      max:Math.max(0,(estimate?.max||0)-elapsed,remaining*1.25),samples};
  }
  const own=timing(job);
  if(!own)return {status:'estimating',sample_count:0};
  let {min,max,remaining}=own;
  if(job.status==='pending'){
    const ahead=await all(`SELECT selected_rule_ids_json,status,started_at,created_at,updated_at,progress_json FROM paper_lint_jobs
      WHERE id!=? AND cancelled_at IS NULL AND (status='running' OR (status='pending' AND rowid<(SELECT rowid FROM paper_lint_jobs WHERE id=?)))`,[job.id,job.id]);
    for(const queued of ahead){
      const wait=timing(queued);if(!wait)return {status:'estimating',sample_count:own.samples};
      min+=wait.min;max+=wait.max;remaining+=wait.remaining;
    }
  }
  return {status:'available',remaining_seconds:Math.ceil(remaining),min_seconds:Math.floor(min),max_seconds:Math.ceil(max),sample_count:own.samples};
}
module.exports={estimateJobEta};
