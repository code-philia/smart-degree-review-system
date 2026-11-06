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
  const own=range(job);
  if(!own)return {status:'estimating',sample_count:0};
  const elapsed=job.status==='running'&&job.started_at?Math.max(0,(now-Date.parse(job.started_at))/1000):0;
  function point(estimate,spent){
    const remaining=estimate.durations.filter(duration=>duration>spent);
    return Math.max(0,remaining.length?remaining[Math.floor(remaining.length/2)]-spent:estimate.max-spent);
  }
  let min=Math.max(0,own.min-elapsed),max=Math.max(0,own.max-elapsed),remaining=point(own,elapsed);
  if(job.status==='running'&&max===0)return {status:'overdue',sample_count:own.samples};
  if(job.status==='pending'){
    const ahead=await all(`SELECT selected_rule_ids_json,status,started_at FROM paper_lint_jobs
      WHERE id!=? AND cancelled_at IS NULL AND (status='running' OR (status='pending' AND rowid<(SELECT rowid FROM paper_lint_jobs WHERE id=?)))`,[job.id,job.id]);
    for(const queued of ahead){
      const wait=range(queued);if(!wait)return {status:'estimating',sample_count:own.samples};
      const spent=queued.status==='running'&&queued.started_at?Math.max(0,(now-Date.parse(queued.started_at))/1000):0;
      // An already-overdue task ahead cannot provide a defensible queue ETA.
      if(spent>=wait.max)return {status:'estimating',sample_count:own.samples};
      min+=Math.max(0,wait.min-spent);max+=Math.max(0,wait.max-spent);remaining+=point(wait,spent);
    }
  }
  return {status:'available',remaining_seconds:Math.ceil(remaining),min_seconds:Math.floor(min),max_seconds:Math.ceil(max),sample_count:own.samples};
}
module.exports={estimateJobEta};
