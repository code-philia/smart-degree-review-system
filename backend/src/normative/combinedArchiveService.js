const db = require('../database/db_runtime');
const COMBINED_JOB_ID = 'archive-479-combined';
const SOURCE_JOB_IDS = [
  '57aa0363-37ac-4ff5-b2c3-b9af12f444fe',
  '4fc9290e-30c9-4d25-8034-2c491882b3e5',
  '5996800a-a75b-4d05-8563-08004a647032',
];
const fail = (status, message) => Object.assign(new Error(message), {status});
const sortRule = (a,b) => Number(a.replace('sjtu_rule_','')) - Number(b.replace('sjtu_rule_',''));

// A read-only view of the three historical scans. Source records and repair
// identities stay intact; papers are joined by complete relative PDF path.
function createCombinedArchiveService(base) {
  let cached;
  async function snapshot(jobs) {
    jobs ||= await base.listJobs();
    const sourceJobs = SOURCE_JOB_IDS.map(id => jobs.find(job => job.id === id));
    if (sourceJobs.some(job => !job || job.status !== 'completed')) return null;
    const key = JSON.stringify(sourceJobs);
    if (cached?.key === key && Date.now() - cached.at < 5000) return cached.promise;
    const promise = load(sourceJobs);
    cached = {key, at:Date.now(), promise};
    try { return await promise; } catch (error) { cached = null; throw error; }
  }
  async function load(sourceJobs) {
    const rows = await db.all(`SELECT id,job_id,relative_path,filename,size_bytes,status,rule_outcomes_json,error_message,
      (SELECT json_group_object(json_extract(r.value,'$.rule_id'),json_array_length(r.value,'$.findings'))
       FROM json_each(result_json,'$.rule_runs') r) AS counts_json
      FROM archive_scan_documents WHERE job_id IN (?,?,?) ORDER BY relative_path,job_id`, SOURCE_JOB_IDS);
    const paths = new Map();
    for (const row of rows) {
      if (!paths.has(row.relative_path)) paths.set(row.relative_path, []);
      paths.get(row.relative_path).push(row);
    }
    if (!paths.size || sourceJobs.some(job => job.total_count !== paths.size) ||
        [...paths.values()].some(group => group.length !== SOURCE_JOB_IDS.length || new Set(group.map(row=>row.job_id)).size !== SOURCE_JOB_IDS.length)) return null;
    const ids = sourceJobs.flatMap(job=>job.selected_rule_ids).sort(sortRule);
    if (new Set(ids).size !== ids.length) return null;
    const documents = [...paths.values()].map(group => {
      group.sort((a,b)=>SOURCE_JOB_IDS.indexOf(a.job_id)-SOURCE_JOB_IDS.indexOf(b.job_id));
      const primary = group[0];
      const counts = Object.assign({}, ...group.map(row=>JSON.parse(row.counts_json || '{}')));
      const outcomes = Object.assign({}, ...group.map(row=>JSON.parse(row.rule_outcomes_json || '{}')));
      const status = group.some(row=>row.status==='failed') ? 'failed' : group.every(row=>row.status==='completed') ? 'completed' : 'pending';
      return {id:primary.id,job_id:COMBINED_JOB_ID,relative_path:primary.relative_path,filename:primary.filename,size_bytes:primary.size_bytes,
        status,error_message:group.map(row=>row.error_message).filter(Boolean).join('；') || null,
        finding_count:Object.values(counts).reduce((n,count)=>n+(Number(count)||0),0),rule_outcomes:outcomes,counts,sources:group};
    });
    const rule_statistics = ids.map(rule_id => ({rule_id,
      finding_count:documents.reduce((n,doc)=>n+(Number(doc.counts[rule_id])||0),0),
      paper_count:documents.filter(doc=>Number(doc.counts[rule_id])>0).length,
    }));
    const job = {...sourceJobs[0],id:COMBINED_JOB_ID,source_job_ids:SOURCE_JOB_IDS,selected_rule_ids:ids,selected_rule_ids_json:JSON.stringify(ids),
      status:'completed',total_count:documents.length,completed_count:documents.filter(doc=>doc.status==='completed').length,
      failed_count:documents.filter(doc=>doc.status==='failed').length,
      inconclusive_count:documents.filter(doc=>Object.values(doc.rule_outcomes).includes('inconclusive')).length,
      finding_count:documents.reduce((n,doc)=>n+doc.finding_count,0),violating_paper_count:documents.filter(doc=>doc.finding_count>0).length,
      created_at:sourceJobs.map(job=>job.created_at).sort().at(-1),finished_at:sourceJobs.map(job=>job.finished_at).filter(Boolean).sort().at(-1)||null,rule_statistics};
    return {job,documents};
  }
  async function required() {
    const data = await snapshot();
    if (!data) throw fail(404,'归档汇总任务不存在或来源扫描尚未完整');
    return data;
  }
  async function primary(documentId) {
    const data = await required();
    const document = data.documents.find(doc=>doc.id===documentId);
    if (!document) throw fail(404,'归档论文结果不存在');
    return document;
  }
  return {...base,
    get rules() {return base.rules;},
    async listJobs() {
      const jobs = await base.listJobs(); const data = await snapshot(jobs);
      if (!data) return jobs;
      const output=[];let added=false;
      for(const job of jobs) {
        if(SOURCE_JOB_IDS.includes(job.id)) {if(!added){output.push(data.job);added=true;}}
        else output.push(job);
      }
      return output;
    },
    async getJob(id) {return id===COMBINED_JOB_ID ? (await required()).job : base.getJob(id);},
    async deleteJob(id) {
      if(id===COMBINED_JOB_ID) throw fail(409,'汇总任务保留原始扫描记录，不支持直接删除');
      return base.deleteJob(id);
    },
    async listDocuments(id, {ruleId,outcome,query,page=1}={}) {
      if(id!==COMBINED_JOB_ID) return base.listDocuments(id,{ruleId,outcome,query,page});
      const data=await required();
      const rows=data.documents.map(({counts,sources,...doc})=>({...doc,finding_count:ruleId?(Number(counts[ruleId])||0):doc.finding_count})).filter(doc=>
        (!ruleId || doc.rule_outcomes[ruleId]) && (!query || doc.relative_path.toLowerCase().includes(String(query).toLowerCase())) &&
        (!outcome || (outcome==='failed'?doc.status==='failed':ruleId?doc.rule_outcomes[ruleId]===outcome:Object.values(doc.rule_outcomes).includes(outcome))));
      const pageNumber=Math.max(1,Math.floor(Number(page)||1));
      return {items:rows.slice((pageNumber-1)*25,pageNumber*25),total:rows.length,
        finding_count:rows.reduce((n,doc)=>n+doc.finding_count,0),violating_paper_count:rows.filter(doc=>doc.finding_count>0).length,page:pageNumber,page_size:25};
    },
    async getDocument(id,documentId) {
      if(id!==COMBINED_JOB_ID) return base.getDocument(id,documentId);
      const document=await primary(documentId);
      const sources=await Promise.all(document.sources.map(row=>base.getDocument(row.job_id,row.id)));
      const runs=sources.flatMap(doc=>doc.result?.rule_runs||[]).sort((a,b)=>sortRule(a.rule_id,b.rule_id));
      const repair_sources={};for(const doc of sources)for(const run of doc.result?.rule_runs||[])repair_sources[run.rule_id]={job_id:doc.job_id,document_id:doc.id};
      const mergedSummary={};
      for(const doc of sources)for(const [key,value] of Object.entries(doc.result?.summary||{})) {
        if(typeof value==='number') mergedSummary[key]=(mergedSummary[key]||0)+value;
      }
      const {counts,sources:ignored,...summary}=document;
      return {...summary,repair_sources,result:{...sources[0].result,rule_runs:runs,
        ruleset:{...sources[0].result?.ruleset,id:COMBINED_JOB_ID,name:'已上线规则归档汇总',version_number:1,version_label:'stored-scans-combined-v1'},
        summary:{...mergedSummary,rule_count:runs.length,finding_count:document.finding_count,issue_rule_count:runs.filter(run=>run.findings?.length).length},
        finding_reviews:sources.flatMap(doc=>doc.result?.finding_reviews||[])}};
    },
    async archivePdfPath(id,documentId) {
      if(id!==COMBINED_JOB_ID) return base.archivePdfPath(id,documentId);
      const document=await primary(documentId);const source=document.sources[0];
      return base.archivePdfPath(source.job_id,source.id);
    },
  };
}
module.exports={COMBINED_JOB_ID,SOURCE_JOB_IDS,createCombinedArchiveService};
