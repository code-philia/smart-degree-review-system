const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const {execFile} = require('node:child_process');
const {promisify} = require('node:util');
const execute = promisify(execFile);
const MAX_MODEL_BYTES = 4 * 1024 * 1024;
let active = 0;
const users = new Set();
function failure(status, message) { return Object.assign(new Error(message), {status}); }
const categories=new Map(Object.entries({'严重错误':'Critical','严重':'Critical',error:'Critical',Critical:'Critical','警告':'Warnings',warning:'Warnings',Warnings:'Warnings','规则未实现警告':'Unverified',Unverified:'Unverified','提示':'Info',info:'Info',Info:'Info'}));
function severity(value) { return categories.get(value); }
const statuses=new Map(Object.entries({'通过':'passed',Passed:'passed','发现问题':'issues', 'Issues found':'issues','无法判定':'inconclusive',Inconclusive:'inconclusive','不适用':'not_applicable','Not applicable':'not_applicable','执行失败':'error',Failed:'error','未能检测':'unsupported','Not completed':'unsupported','待人工复核':'manual','Manual review needed':'manual','未触发告警':'no_alert','No confirmed alerts':'no_alert','发现问题（部分未检测）':'partial','Issues found (partially checked)':'partial','Findings available; some checks incomplete':'partial'}));
function validateExportModel(model, reportId) {
  const invalid = () => { throw failure(400, '导出报告内容无效，请刷新报告后重试。'); };
  if (!model || model.schema_version !== 1 || !Array.isArray(model.reports) || model.reports.length !== 1) invalid();
  if (Buffer.byteLength(JSON.stringify(model), 'utf8') > MAX_MODEL_BYTES) throw failure(413, '报告内容过大，请联系系统管理员。');
  function object(value) { if (!value || typeof value!=='object' || Array.isArray(value)) invalid(); }
  function text(value, max = 100000) { if (typeof value !== 'string' || value.length > max) invalid(); }
  function identifier(value, max = 100000) { text(value,max); if (/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/.test(value)) invalid(); }
  function list(value, max) { if (!Array.isArray(value) || value.length > max) invalid(); }
  function texts(value) { list(value, 1000); value.forEach(item => text(item)); }
  function integer(value) { if (!Number.isSafeInteger(value) || value < 0 || value > 1000000) invalid(); }
  model.reports.forEach((report, index) => {
    object(report);
    if (report.report_id !== reportId || !['zh-CN','en'].includes(report.language)) invalid();
    object(report.document);object(report.summary);
    if (report.signature!==undefined) { object(report.signature); for(const key of ['system','institution','website'])text(report.signature[key],2000); }
    text(report.document.filename, 2000); text(report.document.title || '', 10000);
    for (const key of ['conclusion','ruleset','notice','created_at','detection_type']) text(report[key]);
    for (const count of Object.values(report.summary)) integer(count);
    for (const field of ['page_count','word_count']) if (report.document[field] != null) integer(report.document[field]);
    list(report.findings, 5000); list(report.scope, 1000); list(report.rules, 1000);
    for (const scope of report.scope) { object(scope); identifier(scope.id); for (const key of ['title','description']) text(scope[key]); }
    for (const rule of report.rules) {
      object(rule);identifier(rule.id);for(const key of ['execution_status','outcome'])if(rule[key]!==undefined)identifier(rule[key],100);
      for (const key of ['title','status','message']) text(rule[key]);
      integer(rule.finding_count); list(rule.details, 5000);
      for (const detail of rule.details) { object(detail);text(detail.text); if (!['title','heading','subheading','meta','text','quote','notice','label'].includes(detail.kind)) invalid(); }
    }
    for (const finding of report.findings) {
      object(finding);
      integer(finding.number);
      identifier(finding.id);identifier(finding.rule_id);
      for (const key of ['rule_title','severity','message']) text(finding[key]);
      for (const key of ['suggestions','basis','evidence']) texts(finding[key]);
      for (const key of ['source_basis_indices','source_suggestion_indices']) if (finding[key] !== undefined) {
        list(finding[key], 1000); const target=key==='source_basis_indices'?finding.basis:finding.suggestions;
        for (const value of finding[key]) if (!Number.isInteger(value) || value<0 || value>=target.length) invalid();
      }
      list(finding.locations, 1000);
      for (const location of finding.locations) {
        object(location);
        text(location.label); text(location.text); integer(location.page); if (!location.page) invalid();
        if (location.marks !== undefined) {
          list(location.marks, 1000); let end=0;
          for (const mark of location.marks) { object(mark);if (!Number.isInteger(mark.start) || !Number.isInteger(mark.end) || mark.start<end || mark.end<=mark.start || mark.end>location.text.length) invalid(); end=mark.end; }
        }
      }
    }
    for(const field of ['scope','rules'])if(new Set(report[field].map(item=>item.id)).size!==report[field].length)invalid();
    if(new Set(report.findings.map(item=>item.rule_id+'\u0000'+item.id)).size!==report.findings.length)invalid();
    const totals={Critical:0,Warnings:0,Unverified:0,Info:0};
    for(const item of report.findings){const category=severity(item.severity);if(!category)invalid();totals[category]++;if(!report.rules.some(rule=>rule.id===item.rule_id))invalid();}
    for(const [key,category]of [['finding_count',null],['error_finding_count','Critical'],['warning_finding_count','Warnings'],['execution_warning_count','Unverified'],['info_finding_count','Info']]){
      if((report.summary[key] ?? 0)!==(category?totals[category]:report.findings.length))invalid();
    }
    for(const rule of report.rules){if(rule.finding_count!==report.findings.filter(item=>item.rule_id===rule.id).length)invalid();const state=statuses.get(rule.status);if(rule.execution_status==='error'&&state!=='error'&&state!=='partial')invalid();if(rule.execution_status==='unsupported'&&state!=='unsupported'&&state!=='partial')invalid();}
  });

  return model;
}
function safeFilename(value) {
  return Array.from(String(value).replace(/\.[^.]+$/, '').replace(/[<>:"/\\|?*\u0000-\u001f]/g,'_').trim()).slice(0,100).join('').replace(/[. ]+$/,'') || '论文';
}
async function renderReport({userId,report,model,format,signal}) {
  if(!['pdf','image'].includes(format))throw failure(400,'暂不支持此导出格式。');
  validateExportModel(model,report.id);
  if(active>=2 || users.has(userId))throw failure(429,'报告正在导出，请稍后重试。');
  active++;users.add(userId);
  let directory;
  try {
    directory=await fs.mkdtemp(path.join(os.tmpdir(),'smartdegree-export-'));
    // Canonical report identity cannot be supplied by the browser.
    const normalized=structuredClone(model);
    for(const edition of normalized.reports) {
      edition.document.filename=report.source_filename;
      edition.created_at=report.created_at;
    }
    await fs.writeFile(path.join(directory,'model.json'),JSON.stringify(normalized),{mode:0o600});
    const script=path.join(__dirname,'reportExportRenderer.py');
    await execute(process.env.REPORT_EXPORT_PYTHON || '/usr/bin/python3',[script,directory,format],{
      timeout:120000,maxBuffer:65536,signal,killSignal:'SIGTERM',
      env:{...process.env,PYTHONUTF8:'1'},
    });
    const output=path.join(directory,format==='pdf'?'report.pdf':'report-images.zip');
    const size=(await fs.stat(output)).size;
    if(size>40*1024*1024)throw failure(413,'导出文件过大，请联系系统管理员。');
    return {content:await fs.readFile(output),contentType:format==='pdf'?'application/pdf':'application/zip',filename:safeFilename(report.source_filename)+(normalized.reports[0].language==='en'?'_Review_Report':'_检测报告')+(format==='pdf'?'.pdf':normalized.reports[0].language==='en'?'_Images.zip':'_图片.zip')};
  } catch(error) {
    if(error.status)throw error;
    if(error.name==='AbortError')throw error;
    if(String(error.stderr || '').includes('EXPORT_TOO_MANY_PAGES'))throw failure(413,'导出文件过大，请联系系统管理员。');
    const timeout=error.killed || error.code==='ETIMEDOUT';
    throw failure(timeout?504:503,timeout?'报告导出超时，请稍后重试。':'报告导出暂不可用，请稍后重试。');
  } finally {
    if(directory)await fs.rm(directory,{recursive:true,force:true}).catch(()=>{});
    active--;users.delete(userId);
  }
}
module.exports={validateExportModel,renderReport,MAX_MODEL_BYTES};
