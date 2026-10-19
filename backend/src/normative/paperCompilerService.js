const { execFile } = require('child_process');
const { promisify } = require('util');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { summarizeRuleRuns } = require('./localFiveRulePaperLintService');
const exec = promisify(execFile);
const SCRIPT = path.resolve(__dirname, '../../scripts/paper_compiler_cli.py');
const DEFINITIONS = [[31, '文内引注与文后参考文献格式'], [32, '引用的外部文献不存在'], [33, '引用目的与被引内容无关']];
const IDS = new Set(DEFINITIONS.map(([n]) => `sjtu_rule_${n}`));
const TERMINAL = new Set(['PASS','VIOLATION','UNKNOWN','ERROR','NOT_APPLICABLE']);
function failure(status, code, message) { return Object.assign(new Error(message), { status, code }); }
function isCompilerRuleId(id) { return IDS.has(id); }
function packagePath(number) { return path.join(process.env.PAPER_COMPILER_PACKAGE_ROOT || '', String(number)); }
function getCompilerRules() {
  return DEFINITIONS.map(([number,title]) => ({number, rule_id:`sjtu_rule_${number}`, title:`规则 ${number} · ${title}`,
    description:'仅展示经规范与原文复核确认的告警。', default_severity:'warning', default_enabled:false,
    execution_mode:'semantic', uses_external_model:true, source:'sjtu-paper-compiler',
    available:process.env.PAPER_COMPILER_ENABLED === '1' && Boolean(process.env.PAPER_COMPILER_PACKAGE_ROOT) && fs.existsSync(path.join(packagePath(number),'manifest.json')) }));
}
async function runJsonProcess(command,args,{signal,timeoutMs=1200000,maxBytes=64*1024*1024,allowArray=false}={}) {
  if (!Number.isSafeInteger(timeoutMs) || timeoutMs<1 || timeoutMs>7200000 || !Number.isSafeInteger(maxBytes) || maxBytes<1 || maxBytes>128*1024*1024) throw new TypeError('Invalid compiler resource budget');
  if(signal?.aborted) throw failure(504,'COMPILER_ABORTED','规则编译检测已取消');
  let stdout;
  try { ({stdout}=await exec(command,args,{signal,timeout:timeoutMs,maxBuffer:maxBytes,encoding:'utf8',windowsHide:true,killSignal:'SIGKILL',env:{...process.env,PYTHONIOENCODING:'utf-8'}})); }
  catch(error) {
    if(error.code==='ERR_CHILD_PROCESS_STDIO_MAXBUFFER') throw failure(502,'COMPILER_OUTPUT_LIMIT','规则编译检测输出超过资源上限');
    if(signal?.aborted || error.name==='AbortError' || error.killed) throw failure(504,'COMPILER_INTERRUPTED','规则编译检测超时或已取消');
    let stopped;
    try { stopped=JSON.parse(typeof error.stdout==='string' ? error.stdout : ''); } catch {}
    if(stopped?.status==='error' && stopped.error_type==='BudgetExceeded')throw failure(429,'COMPILER_BUDGET_EXHAUSTED','API预算已达到上限，未完成的检测已停止');
    if(stopped?.status==='error' && stopped.error_type==='RequestDeadlineExceeded')throw failure(504,'COMPILER_TIME_LIMIT','本次任务已达到时限，未完成的检测已停止');
    throw failure(error.code==='ENOENT'?503:502,'COMPILER_PROCESS_FAILED','规则编译检测未完成，请检查运行记录');
  }
  try { const result=JSON.parse(stdout);if(!result || typeof result!=='object' || (Array.isArray(result) && !allowArray))throw new Error();return result; }
  catch { throw failure(502,'COMPILER_INVALID_JSON','规则编译检测返回了无效结果'); }
}
function toCompilerResult(output,selectedRuleIds) {
  if(output?.schema_version!=='paper-check/1.0' || !Array.isArray(output.rules))throw failure(502,'COMPILER_INVALID_REPORT','规则编译检测结果不完整');
  const publication=output.publication?.public;
  if(publication && (!['ALERT','NO_ALERT'].includes(publication.status) || !Array.isArray(publication.findings) ||
      (publication.status==='NO_ALERT' && publication.findings.length)))throw failure(502,'COMPILER_INVALID_REPORT','告警复核结果不完整');
  const asVersion=value=>typeof value==='string' && value.trim() ? value : null;
  const executionReason=value=>value?.error_type==='ProgramError' && typeof value.reason==='string' && value.reason.length<=1000 && value.reason.trim() ? value.reason : null;
  const refinementMessage=new Map([
    ['budget_limit','自动迭代因API预算或时限停止；已完成的检测结果保留，未完成项无法判定。'],
    ['mutation_validation_incomplete','自动迭代验证尚未完成，继续使用当前版本；本次检测结果保留。'],
    ['candidate_rejected','自动迭代候选未通过验证，继续使用当前版本；本次检测结果保留。'],
    ['audit_or_execution_error','自动迭代未完成，继续使用当前版本；本次检测结果保留。'],
    ['execution_error_unrecoverable','自动迭代因基线执行异常停止，继续使用当前版本；本次检测结果保留。'],
  ]).get(output.runtime?.status) || null;
  const baselineReasons=output.runtime?.status==='execution_error_unrecoverable' && Array.isArray(output.runtime.unrecoverable_baseline_failures)
    ? output.runtime.unrecoverable_baseline_failures.slice(0,3).map(executionReason).filter(Boolean) : [];
  const baselineMessage=baselineReasons.length ? `基线执行异常：${baselineReasons.join('；')}` : null;
  const explicitReport=output.runtime?.report_version;
  const runtimeVersion=explicitReport ? asVersion(explicitReport.suite_version) : asVersion(output.runtime?.active_version) || asVersion(output.runtime_version);
  const pipelineVersion=asVersion(output.pipeline_version) || asVersion(output.pipeline?.version_id);
  const versionLabel=runtimeVersion || pipelineVersion || '兼容规则包';
  const state=explicitReport ? output.runtime?.current_snapshot || output.runtime : output.runtime;
  const runtimeSnapshot=typeof state?.freeze==='boolean' && Number.isSafeInteger(state.generation) && state.generation>=0
    ? {freeze:state.freeze,generation:state.generation,active_version:asVersion(state.active_version),
        ...(explicitReport ? {report_version:runtimeVersion} : {})} : null;
  const ruleRuns=selectedRuleIds.map(ruleId=>{
    if(!IDS.has(ruleId))throw failure(400,'COMPILER_UNKNOWN_RULE','未知编译规则');
    const rows=output.rules.filter(r=>String(r.rule_id)===ruleId.slice(10));
    const raw=rows[0];
    if(rows.length!==1 || !TERMINAL.has(raw?.status) || !Array.isArray(raw.results) || raw.results.some(r=>!TERMINAL.has(r.status)))throw failure(502,'COMPILER_PARTIAL_REPORT','所选规则缺少完整终态记录');
    const basisDetails=r=>(r.basis || []).map(id=>(raw.basis_catalog || []).find(b=>b.id===id) || {id,kind:id.startsWith('gbt')?'standard':'project'});
    let findings=raw.results.filter(r=>r.status==='VIOLATION').map((r,index)=>({finding_id:`${ruleId}_${index+1}`,rule_id:ruleId,
      message:r.message || '发现规则不符合项',suggestion:null,location:r.location_mode==='synthetic'?null:r.location || null,anchors:[],
      evidence:r.display_evidence || [],basis_details:basisDetails(r),source_kind:r.location_mode,node_id:r.node_id,check_id:r.check_id}));
    if(publication) findings=raw.status==='ERROR' ? [] : publication.findings.filter(f=>String(f.rule_id)===ruleId.slice(10)).map((f,index)=>{
      const source=raw.results.find(r=>r.node_id===f.node_id && r.location_mode!=='synthetic' && r.location) || {};
      const spans=(f.evidence || []).flat();
      const basisIds=[...new Set(spans.filter(e=>e.kind==='normative_span').map(e=>e.basis_id))];
      return {finding_id:`${ruleId}_confirmed_${index+1}`,rule_id:ruleId,node_id:f.node_id,
        message:f.message || '发现经规范与原文复核确认的问题',suggestion:null,location:source.location || null,anchors:[],
        source_kind:source.location?'source':'unlocated',
        evidence:spans.map((e,i)=>({id:`confirmed-${index}-${i}`,kind:e.kind,quote:e.quote})),
        basis_details:basisIds.map(id=>(raw.basis_catalog || []).find(b=>b.id===id) || {id})};
    });
    const diagnostics=publication ? [] : raw.results.filter(r=>['UNKNOWN','ERROR'].includes(r.status)).map(r=>({node_id:r.node_id,check_id:r.check_id,status:r.status,reasons:r.reasons || [],evidence:r.display_evidence || [],basis_details:basisDetails(r)}));
    const unknown=raw.counts?.UNKNOWN || 0;
    const reason=raw.status==='ERROR' ? executionReason(raw.execution_error) : null;
    return {rule_run_id:`run_${ruleId}`,rule_id:ruleId,severity:'warning',params:null,
      execution_status:raw.status==='ERROR'?'error':'completed',evidence_mode:findings.some(f=>f.source_kind==='synthetic')?'derived':'native',
      outcome:findings.length?'issues_found':publication?'inconclusive':raw.status==='PASS'?'passed':raw.status==='NOT_APPLICABLE'?'not_applicable':'inconclusive',
      ...(publication ? {publication_status:findings.length?'ALERT':'NO_ALERT'} : {}),
      message:publication ? (raw.status==='ERROR' ? `规则执行失败${reason ? '：'+reason : ''}` : findings.length ? '发现经复核确认的告警' : '未触发告警') : [raw.status==='UNKNOWN' || unknown || raw.coverage?.incomplete_scopes?.length ? `${unknown} 项证据不足；未覆盖的内容保留无法判定。` : null,
        reason ? `规则执行异常：${reason}` : null, refinementMessage, baselineMessage].filter(Boolean).join(' ') || null,
      compiler_runtime_status:typeof output.runtime?.status==='string' ? output.runtime.status : null,
      findings,compiler_diagnostics:diagnostics,...(publication ? {} : {coverage:raw.coverage,compiler_counts:raw.counts}),package_sha256:raw.package_sha256,
      runtime_version:runtimeVersion,pipeline_version:pipelineVersion,runtime_snapshot:runtimeSnapshot};
  });
  return {type:'paper_lint',paper_title:'上传论文',runtime:runtimeSnapshot,ruleset:{id:'paper-compiler',name:'引用规则编译检测',version_number:1,version_label:`引用规则 · ${versionLabel}`},rule_runs:ruleRuns,summary:summarizeRuleRuns(ruleRuns)};
}
function compilerBudget(name) {
  const value = process.env[name] === undefined ? '200' : process.env[name].trim();
  if (!/^(?:0|[1-9]\d*)(?:\.\d{1,6})?$/.test(value) || !Number.isFinite(Number(value)) || Number(value) <= 0 || Number(value) > 500)
    throw failure(503,'COMPILER_BUDGET_CONFIG_INVALID','检测预算配置无效，请联系管理员');
  return value;
}
async function runCompilerRules(pdfPath,selectedRuleIds,options={}) {
  const catalog=getCompilerRules();
  if(!selectedRuleIds.length || new Set(selectedRuleIds).size!==selectedRuleIds.length || selectedRuleIds.some(id=>!IDS.has(id)))throw failure(400,'COMPILER_UNKNOWN_RULE','请选择有效编译规则');
  if(selectedRuleIds.some(id=>!catalog.find(r=>r.rule_id===id).available))throw failure(503,'COMPILER_UNAVAILABLE','引用规则尚未启用或规则包未配置');
  const totalBudget=compilerBudget('PAPER_COMPILER_BUDGET_CNY');
  const phaseBudget=compilerBudget('PAPER_COMPILER_PHASE_BUDGET_CNY');
  const resultRoot=process.env.PAPER_COMPILER_RESULT_ROOT || '/data/results/paper-compiler/website';
  await fs.promises.mkdir(resultRoot,{recursive:true,mode:0o700});
  const output=path.join(resultRoot,crypto.randomUUID()+'.json');
  const args=[SCRIPT,'check','--pdf',pdfPath,'--out',output,'--stdout-report','--publication-review','--cache',process.env.PAPER_COMPILER_CACHE_ROOT || '/data/runtime/paper-compiler','--phase','website','--phase-budget',phaseBudget,'--budget',totalBudget,
    ...selectedRuleIds.flatMap(id=>['--package',packagePath(id.slice(10))])];
  const raw=await runJsonProcess(process.env.PAPER_COMPILER_PYTHON || 'python3',args,options);
  if(!raw.publication?.public)throw failure(502,'COMPILER_PUBLICATION_MISSING','告警复核尚未完成');
  return toCompilerResult(raw,selectedRuleIds);
}
function controlRoot() { return path.resolve(process.env.PAPER_COMPILER_CONTROL_ROOT || '/data/runtime/paper-compiler/online'); }
async function runCompilerControl(action,{version}={}) {
  if(!['status','freeze','unfreeze','history','rollback'].includes(action))throw failure(400,'COMPILER_CONTROL_ACTION','请选择有效管理操作');
  if(action==='rollback' && (typeof version!=='string' || !version.trim()))throw failure(400,'COMPILER_CONTROL_VERSION','请选择有效历史版本');
  if(process.env.PAPER_COMPILER_ENABLED!=='1')throw failure(503,'COMPILER_UNAVAILABLE','自动迭代管理尚未启用，请联系管理员配置检测服务');
  const args=[SCRIPT,'control','--action',action,'--control-root',controlRoot()];
  if(action==='rollback')args.push('--version',version);
  let result=await runJsonProcess(process.env.PAPER_COMPILER_PYTHON || 'python3',args,{timeoutMs:45000,maxBytes:4*1024*1024,allowArray:action==='history'});
  if(action==='history' && !Array.isArray(result) && Array.isArray(result.events))result=result.events;
  const valid=action==='history'
    ? Array.isArray(result) && result.every(item=>item && typeof item==='object' && !Array.isArray(item))
    : !Array.isArray(result) && typeof result.freeze==='boolean' && Number.isSafeInteger(result.generation) && result.generation>=0 &&
      (result.active_version===null || typeof result.active_version==='string') && (result.active_path===null || typeof result.active_path==='string');
  if(!valid)throw failure(502,'COMPILER_CONTROL_INVALID','自动迭代管理状态不完整');
  return result;
}
module.exports={getCompilerRules,isCompilerRuleId,runCompilerRules,toCompilerResult,runJsonProcess,runCompilerControl};
