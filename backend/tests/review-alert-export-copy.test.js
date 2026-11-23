import {createRequire} from 'node:module';
import {expect,it} from 'vitest';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
const require=createRequire(import.meta.url);
const {validateExportModel,renderReport}=require('../src/normative/reportExportService');
it.each(['检测异常提醒','Review alerts','规则未实现警告','Unverified'])('accepts %s without changing the execution-alert count',severity=>{
 const model={schema_version:1,reports:[{schema_version:1,language:'en',report_id:'r',document:{filename:'paper.pdf'},
  conclusion:'Review incomplete',ruleset:'v1',notice:'Review manually',created_at:'2026-11-23',detection_type:'review',
  summary:{finding_count:1,error_finding_count:0,warning_finding_count:0,info_finding_count:0,execution_warning_count:1},
  scope:[{id:'rule',title:'References',description:'Check references'}],
  rules:[{id:'rule',title:'References',status:'Not completed',execution_status:'unsupported',outcome:'inconclusive',message:'Unavailable',finding_count:1,details:[]}],
  findings:[{number:1,id:'f',rule_id:'rule',rule_title:'References',severity,message:'Unavailable',suggestions:['Contact j82279240@gmail.com'],basis:[],evidence:[],locations:[]}]}]};
 const original=JSON.stringify(model);expect(validateExportModel(model,'r')).toBe(model);expect(JSON.stringify(model)).toBe(original);
});
it.each(['zh-CN','en'])('prints the renamed alert category and contact email in the %s PDF',{timeout:120000},async language=>{
 const en=language==='en';
 const model={schema_version:1,reports:[{schema_version:1,language,report_id:'r',document:{filename:'paper.pdf'},
  conclusion:'Review incomplete',ruleset:'v1',notice:'Review manually',created_at:'2026-11-23T00:00:00Z',detection_type:'review',
  summary:{finding_count:1,error_finding_count:0,warning_finding_count:0,info_finding_count:0,execution_warning_count:1},
  scope:[{id:'rule',title:'References',description:'Check references'}],
  rules:[{id:'rule',title:'References',status:'Not completed',execution_status:'unsupported',outcome:'inconclusive',message:'Unavailable',finding_count:1,details:[]}],
  findings:[{number:1,id:'f',rule_id:'rule',rule_title:'References',severity:en?'Review alerts':'检测异常提醒',message:'Unavailable',
   suggestions:[en?'Try again later. If the problem persists, contact the administrator to check the run logs. Contact email: j82279240@gmail.com':'请稍后重试；若持续失败，请联系管理员检查运行记录，联系邮箱：j82279240@gmail.com'],basis:[],evidence:[],locations:[]}]}]};
 const original=JSON.stringify(model);
 const pdf=await renderReport({userId:'alert-copy-'+language,report:{id:'r',source_filename:'paper.pdf',created_at:'2026-11-23T00:00:00Z'},model,format:'pdf'});
 const directory=await fs.mkdtemp(path.join(os.tmpdir(),'review-alert-copy-'));
 try{
  const file=path.join(directory,'report.pdf');await fs.writeFile(file,pdf.content);
  const text=execFileSync(process.env.REPORT_EXPORT_PDFTOTEXT||'/usr/bin/pdftotext',['-enc','UTF-8',file,'-'],{encoding:'utf8'});
  expect(text).toContain(en?'Review alerts: 1':'检测异常提醒 1');
  expect(text.replace(/\s/g,'')).toContain('j82279240@gmail.com');
  expect(text).not.toMatch(/规则未实现警告|Unverified/);
  expect(JSON.stringify(model)).toBe(original);
 }finally{await fs.rm(directory,{recursive:true,force:true});}
});
