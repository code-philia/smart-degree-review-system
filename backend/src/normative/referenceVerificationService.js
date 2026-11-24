const path = require('path');
const { runPaperLintProcess } = require('./paperLintProcess');
const { summarizeRuleRuns } = require('./localFiveRulePaperLintService');

const RULE_ID = 'reference_verification_check';
const referenceVerificationRule = Object.freeze({
  rule_id:RULE_ID, title:'引用文献是否不存在',
  description:'检查是否存在AI编造的、张冠李戴的、已过时的引用',
  family:'reference_database', runner:'reference_database', execution_mode:'deterministic',
  uses_external_model:false, default_severity:'info', default_enabled:false,
  enabled_in_mvp:true, default_selected:false, repair_supported:false, available:true, source:'sjtu-local',
});
const labels = {
  verified:['已核验','Verified'], suspected:['疑似伪造','Suspected fabrication'],
  mismatch:['信息不符','Metadata mismatch'], upgrade:['可升级','Published version available'],
  incomplete:['可补全','Can be completed'], unverified:['未核验','Unverified'],
};
const suggestions = {
  suspected:['公开检索未找到充分的匹配依据，不代表文献一定不存在，请对照原始来源人工复核。','Public searches did not establish a sufficient match. This does not prove nonexistence; review the original source.'],
  mismatch:['请结合数据库来源及原始文献，核对下方不一致的字段。','Check the differing fields against the linked database record and original publication.'],
  upgrade:['已发现相关的正式出版记录，请核对引用的具体版本后决定是否更新。','Review the related published record and the version actually cited before updating.'],
  incomplete:['请对照已核验的数据库记录补全缺失信息。','Complete missing fields using the verified database record.'],
  unverified:['当前信息或检索覆盖不足，请人工核对；未核验不表示引用存在问题。','The available metadata or search coverage is insufficient. Review manually; an unverified result does not establish a citation error.'],
};

async function extractReferences(pdfPath,{signal}={}) {
  const python=process.env.PAPER_MODEL_PYTHON || process.env.FIVE_RULE_PYTHON || process.env.REVIEW_PILOT_PYTHON
    || (process.platform==='win32'?'python':'python3');
  const {stdout}=await runPaperLintProcess(python,[path.resolve(__dirname,'../../scripts/reference_verification_extract.py'),'--pdf',pdfPath],
    {signal,timeoutMs:120000,maxBytes:16*1024*1024,env:{...process.env,PYTHONIOENCODING:'utf-8',PYTHONDONTWRITEBYTECODE:'1'}});
  const result=JSON.parse(stdout);
  if(!Array.isArray(result.entries)||result.entries.length>3000)throw new Error('Invalid bibliography extraction');
  return result;
}
function abortIfNeeded(signal){if(signal?.aborted)throw Object.assign(new Error('Cancelled'),{name:'AbortError'});}
function redactSecrets(value,keys){
  if(typeof value==='string')return keys.reduce((text,key)=>text.split(key).join('[redacted]'),value);
  if(Array.isArray(value))return value.map(item=>redactSecrets(item,keys));
  if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).map(([key,item])=>[key,redactSecrets(item,keys)]));
  return value;
}
function toResult(records,extraction) {
  const counts=Object.fromEntries(Object.keys(labels).map(key=>[key,records.filter(row=>row.category===key).length]));
  const incomplete=!extraction.coverage_complete||records.some(row=>row.category==='unverified'||row.coverage?.complete===false);
  const findings=records.filter(row=>row.category!=='verified').map((row,index)=>({
    finding_id:`${RULE_ID}_${row.entry.id || index}`,rule_id:RULE_ID,
    severity:row.category==='mismatch'?'warning':'info',
    message:`${labels[row.category][0]}：${row.entry.title || row.entry.text || '未可靠识别参考文献列表'}`,
    message_en:`${labels[row.category][1]}: ${row.entry.title || row.entry.text || 'The bibliography could not be reliably extracted'}`,
    suggestion:suggestions[row.category][0],suggestion_en:suggestions[row.category][1],
    location:row.entry.location || null,anchors:[],source_kind:'source',
    evidence:(row.sources || []).filter(source=>source.url).map((source,i)=>({id:`reference-source-${index}-${i}`,kind:'external_source',provider:source.provider,url:source.url,quote:row.matched?.title || source.provider})),
    reference_check:row,
  }));
  const ruleRun={rule_id:RULE_ID,rule_run_id:`run_${RULE_ID}`,severity:'info',execution_status:'completed',evidence_mode:'native',
    outcome:findings.some(f=>['mismatch','suspected'].includes(f.reference_check.category))?'issues_found':incomplete?'inconclusive':findings.length?'issues_found':'passed',
    message:'参考文献核验已完成，请查看逐条结果及数据源覆盖情况。',
    findings,params:{reference_verification:{version:'reference-database/1.0',counts,entries:records,native_only:true,coverage_complete:!incomplete}},
    coverage:{incomplete_scopes:incomplete?['bibliography']:[]}};
  return {type:'paper_lint',paper_title:'上传论文',ruleset:{id:'reference-database',name:'多源参考文献核验',version_number:1,version_label:'reference-database/1.0'},rule_runs:[ruleRun],summary:summarizeRuleRuns([ruleRun])};
}
async function runReferenceVerification(pdfPath,{userId,signal,extractor=extractReferences,verify,credentials,onProgress}={}) {
  abortIfNeeded(signal);
  const extraction=await extractor(pdfPath,{signal});
  const secretOptions=credentials || (userId?await require('../auth/referenceSettingsService').getReferenceCredentials(userId):{});
  const secretKeys=[secretOptions.personalKey,secretOptions.serpapiKey,...(secretOptions.platformKeys || [])].filter(key=>typeof key==='string'&&key);
  verify ||= require('./referenceVerificationCore').verifyReference;
  if(!extraction.entries.length)return toResult([{category:'unverified',reason_code:'bibliography_not_extracted',
    entry:{id:'unreadable',text:'',title:'',location:null},sources:[],comparisons:[],coverage:{complete:false}}],extraction);
  const records=new Array(extraction.entries.length);
  let next=0,done=0;
  async function worker(){
    while(next<extraction.entries.length){
      abortIfNeeded(signal);
      const index=next++,entry=extraction.entries[index];
      let result;
      try {result=await verify(entry,{...secretOptions,signal});}
      catch(error){abortIfNeeded(signal);if(error?.name==='AbortError')throw error;
        result={category:'unverified',reason_code:'provider_unavailable',sources:[],comparisons:[],coverage:{complete:false}};}
      if(!labels[result.category])result={category:'unverified',reason_code:'invalid_provider_result',sources:[],comparisons:[],coverage:{complete:false}};
      records[index]=redactSecrets({...result,entry},secretKeys);
      done++;
      if(onProgress&&(done%10===0||done===records.length))await onProgress({completed:done,total:records.length});
    }
  }
  await Promise.all(Array.from({length:Math.min(3,records.length)},worker));
  abortIfNeeded(signal);
  return toResult(records,extraction);
}
module.exports={RULE_ID,referenceVerificationRule,extractReferences,runReferenceVerification,toResult};
