import {createRequire} from 'node:module';
import {beforeAll,afterAll,expect,it} from 'vitest';
import express from 'express';import request from 'supertest';
import fs from 'node:fs/promises';import os from 'node:os';import path from 'node:path';import {execFileSync} from 'node:child_process';
const require=createRequire(import.meta.url);
const {validateExportModel,renderReport}=require('../src/normative/reportExportService');
const {createReportExportRouter}=require('../src/normative/reportExportRoutes');
const {createTestDatabaseHarness,get}=require('../src/database');
const {createUserSession}=require('../src/auth/sessionService');
let harness,cookie;
function sample(language='zh-CN',id='report-1'){
 const en=language==='en';return {schema_version:1,reports:[{schema_version:1,language,report_id:id,
 document:{filename:'论文.pdf',title:'sample',page_count:5,word_count:100},created_at:'2026-11-11T08:30:00Z',detection_type:'review',ruleset:'v1',conclusion:en?'Some checks failed.':'部分检查失败。',
 summary:{finding_count:1,error_finding_count:0,warning_finding_count:1,info_finding_count:0,execution_warning_count:0},notice:en?'Review manually.':'请人工复核。',
 scope:[{id:'r1',title:en?'Punctuation':'标点检查',description:en?'Check punctuation.':'核对标点。'}],rules:[{id:'r1',title:en?'Punctuation':'标点检查',execution_status:'error',outcome:'inconclusive',status:en?'Failed':'执行失败',message:en?'Unavailable':'暂不可用',finding_count:1,details:[{kind:'quote',text:'原文\\input{/etc/passwd}% & # _ $'}]}],
 findings:[{number:1,id:'f1',rule_id:'r1',rule_title:en?'Punctuation':'标点检查',severity:en?'Warnings':'警告',message:en?'Review punctuation.':'请核对标点。',locations:[{label:en?'Chinese abstract source':'中文摘要原句',page:2,text:'原文,示例',marks:[{start:2,end:3}]}],suggestions:[en?'Review this finding.':'请核对本项结果。'],basis:[],evidence:['Source evidence.']}]}]};
}
beforeAll(async()=>{harness=createTestDatabaseHarness({label:'report-export',seedDefault:true});await harness.setup();const session=await createUserSession(await get("SELECT * FROM auth_users WHERE id='student01'"));cookie='arc_session='+session.sessionId;});
afterAll(async()=>harness.cleanup());
function app(generate=async()=>({content:Buffer.from('%PDF-1.7\npreview'),filename:'paper.pdf',contentType:'application/pdf'})){
 const value=express();value.use('/api/normative/paper-lint',createReportExportRouter({getReport:async(id,user)=>id==='report-1'&&user==='student01'?{id,source_filename:'论文.pdf',created_at:'2026-11-11T08:30:00Z'}:null,generate}));return value;
}
it('requires login and protects reports owned by another account',async()=>{
 await request(app()).post('/api/normative/paper-lint/reports/report-1/export').send({}).expect(401);
 await request(app()).post('/api/normative/paper-lint/reports/other/export').set('Cookie',cookie).send({format:'pdf',model:sample('en','other')}).expect(404);
});
it('returns a private downloadable single-language attachment after checking ownership',async()=>{
 let received;const response=await request(app(async input=>{received=input;return {content:Buffer.from('%PDF-1.7\npreview'),filename:'论文_检测报告.pdf',contentType:'application/pdf'};})).post('/api/normative/paper-lint/reports/report-1/export').set('Cookie',cookie).send({format:'pdf',model:sample()}).expect(200);
 expect(received.userId).toBe('student01');expect(received.model.reports).toHaveLength(1);expect(response.headers['cache-control']).toContain('no-store');expect(response.headers['content-disposition']).toContain('attachment');
});
it('accepts either language but rejects combined, unsupported or inconsistent documents',()=>{
 for(const language of ['zh-CN','en'])expect(validateExportModel(sample(language),'report-1').reports[0].language).toBe(language);
 for(const mutate of [m=>m.reports.push(structuredClone(m.reports[0])),m=>m.reports[0].language='fr',m=>m.reports[0].report_id='other',m=>m.reports[0].summary.finding_count=0,m=>m.reports[0].findings[0].severity='constructor',m=>m.reports[0].rules.push({...m.reports[0].rules[0]}),m=>m.reports[0].scope.push({...m.reports[0].scope[0]}),m=>m.reports[0].rules[0].status='Passed',m=>m.reports[0].findings[0].locations[0].marks=[{start:0,end:999}]]){
  const model=sample();mutate(model);expect(()=>validateExportModel(model,'report-1')).toThrowError(expect.objectContaining({status:400}));
 }
});
it('rejects null nested data and unsupported formats with structured errors',async()=>{
 for(const mutate of [m=>m.reports[0].scope[0]=null,m=>m.reports[0].rules[0]=null,m=>m.reports[0].findings[0].locations[0]=null,m=>m.reports[0].signature=null]){
  const model=sample();mutate(model);expect(()=>validateExportModel(model,'report-1')).toThrowError(expect.objectContaining({status:400}));
 }
 await request(app()).post('/api/normative/paper-lint/reports/report-1/export').set('Cookie',cookie).send({format:'html',model:sample()}).expect(400);
});
it('bounds per-user concurrency, cancels child processes and releases the renderer slot',async()=>{
 const controller=new AbortController();const report={id:'report-1',source_filename:'论文.pdf',created_at:'2026-11-11T08:30:00Z'};
 const first=renderReport({userId:'cancel-user',report,model:sample(),format:'pdf',signal:controller.signal});
 await expect(renderReport({userId:'cancel-user',report,model:sample(),format:'pdf'})).rejects.toMatchObject({status:429});
 controller.abort();await expect(first).rejects.toMatchObject({name:'AbortError'});
});
it.each(['zh-CN','en'])('compiles true LaTeX in %s only, preserving source labels, symbols and highlighted spaces',{timeout:120000},async language=>{
 const symbols='Greek α β γ Δ λ ∑ ∞ ∫ ℝ 𝑥 € ± ≥ ≤ → × μ Ω Å é — 中文';
 const model=sample(language),finding=model.reports[0].findings[0];
 finding.locations[0]={...finding.locations[0],text:symbols+' alpha beta gamma delta '+ '示例'.repeat(40),marks:[{start:symbols.length+1,end:symbols.length+103}]};
 finding.message+=' \\input{/etc/passwd} & % # _ $ { } ~ ^';
 const report={id:'report-1',source_filename:'原始论文.pdf',created_at:'2026-11-11T08:30:00Z'};
 const pdf=await renderReport({userId:'unicode',report,model,format:'pdf'});
 expect(pdf.content.subarray(0,5).toString()).toBe('%PDF-');
 const dir=await fs.mkdtemp(path.join(os.tmpdir(),'export-test-'));
 try{const file=path.join(dir,'check.pdf');await fs.writeFile(file,pdf.content);const text=execFileSync(process.env.REPORT_EXPORT_PDFTOTEXT || '/usr/bin/pdftotext',['-enc','UTF-8',file,'-'],{encoding:'utf8'});
  for(const char of ['α','β','γ','λ','∑','∫','ℝ','𝑥','≥','≤','μ'])expect(text).toContain(char);
  expect(text.replace(/\s/g,'')).toContain('示例'.repeat(40));expect(text).toContain('alpha beta gamma delta');
  expect(text).toContain(language==='en'?'Chinese abstract source':'中文摘要原句');
  expect(text).toContain(language==='en'?'Thesis compliance report':'论文规范性检测报告');
  expect(text).not.toContain(language==='en'?'检测综述':'Review summary');
 }finally{await fs.rm(dir,{recursive:true,force:true});}
});
it('renders all pages into PNG images rather than truncating the attachment',{timeout:120000},async()=>{
 const images=await renderReport({userId:'image',report:{id:'report-1',source_filename:'论文.pdf',created_at:'2026-11-11T08:30:00Z'},model:sample('en'),format:'image'});
 expect(images.content.subarray(0,2).toString()).toBe('PK');expect(images.contentType).toBe('application/zip');
});
it('uses the configured PDF inspection tool rather than a system-disk binary',{timeout:120000},async()=>{
 const previous=process.env.REPORT_EXPORT_PDFINFO;
 process.env.REPORT_EXPORT_PDFINFO='/nonexistent-export-pdfinfo';
 try{await expect(renderReport({userId:'tool-path',report:{id:'report-1',source_filename:'论文.pdf',created_at:'2026-11-11T08:30:00Z'},model:sample(),format:'pdf'})).rejects.toMatchObject({status:503});}
 finally{if(previous===undefined)delete process.env.REPORT_EXPORT_PDFINFO;else process.env.REPORT_EXPORT_PDFINFO=previous;}
});


it('renders nonprinting source controls without changing raw evidence or literal TeX',{timeout:120000},async()=>{
 const model=sample('en'),finding=model.reports[0].findings[0];
 const controls=String.fromCharCode(...[0,1,2,3,4,5,6,7,8,11,12,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31]);
 finding.locations[0]={...finding.locations[0],text:'A\u0000wrong\u0001token',marks:[{start:2,end:7}]};
 finding.evidence=['Original'+controls+'source evidence\nWith\tliteral \\input{/etc/passwd} and α ≥ ℝ'];
 finding.basis=['Source\u0000basis'];finding.source_basis_indices=[0];
 model.reports[0].rules[0].details.push({kind:'quote',text:'Quoted\u0001source'});
 const before=JSON.stringify(model);
 const pdf=await renderReport({userId:'source-controls',report:{id:'report-1',source_filename:'论文.pdf',created_at:'2026-11-11T08:30:00Z'},model,format:'pdf'});
 expect(JSON.stringify(model)).toBe(before);
 const directory=await fs.mkdtemp(path.join(os.tmpdir(),'export-controls-'));
 try{const file=path.join(directory,'report.pdf');await fs.writeFile(file,pdf.content);
  const text=execFileSync(process.env.REPORT_EXPORT_PDFTOTEXT||'/usr/bin/pdftotext',['-enc','UTF-8',file,'-'],{encoding:'utf8'}),compact=text.replace(/\s/g,'');
  for(const value of ['Awrongtoken','Originalsourceevidence','Sourcebasis','Quotedsource','\\input{/etc/passwd}','α','≥','ℝ'])expect(compact).toContain(value);
  expect(text).not.toMatch(/root:x:0:0/);
 }finally{await fs.rm(directory,{recursive:true,force:true});}
});

it('preserves circled numerals in original source quotations',{timeout:120000},async()=>{
 const model=sample('en');model.reports[0].findings[0].locations[0]={label:'Original source',page:2,text:'① first ② second ③ third',marks:[]};
 const before=JSON.stringify(model);
 const pdf=await renderReport({userId:'circled-source',report:{id:'report-1',source_filename:'论文.pdf',created_at:'2026-11-11T08:30:00Z'},model,format:'pdf'});
 expect(JSON.stringify(model)).toBe(before);
 const directory=await fs.mkdtemp(path.join(os.tmpdir(),'export-circled-'));
 try{const file=path.join(directory,'report.pdf');await fs.writeFile(file,pdf.content);const text=execFileSync(process.env.REPORT_EXPORT_PDFTOTEXT||'/usr/bin/pdftotext',['-enc','UTF-8',file,'-'],{encoding:'utf8'});for(const symbol of ['①','②','③'])expect(text).toContain(symbol);}finally{await fs.rm(directory,{recursive:true,force:true});}
});


it('keeps canonical report identity and machine identifiers strict when source controls are accepted',()=>{
 for(const mutate of [m=>m.reports[0].report_id+='\u0000',m=>{const r=m.reports[0];r.scope[0].id+='\u0000';r.rules[0].id+='\u0000';r.findings[0].rule_id+='\u0000';}]){const model=sample();mutate(model);expect(()=>validateExportModel(model,'report-1')).toThrowError(expect.objectContaining({status:400}));}
});


it('keeps literal ASCII quote punctuation in technical source excerpts',{timeout:120000},async()=>{
 const source="Tram`er O'Neil ``quoted'' --flag ---option \"quoted\" <<left>>";
 const model=sample('en');model.reports[0].findings[0].locations[0]={label:'Original source',page:2,text:source,marks:[]};
 const pdf=await renderReport({userId:'literal-source-punctuation',report:{id:'report-1',source_filename:'论文.pdf',created_at:'2026-11-11T08:30:00Z'},model,format:'pdf'});
 const directory=await fs.mkdtemp(path.join(os.tmpdir(),'export-punctuation-'));
 try{const file=path.join(directory,'report.pdf');await fs.writeFile(file,pdf.content);const text=execFileSync(process.env.REPORT_EXPORT_PDFTOTEXT||'/usr/bin/pdftotext',['-enc','UTF-8',file,'-'],{encoding:'utf8'});expect(text.replace(/\s/g,'')).toContain("Tram`erO'Neil``quoted''--flag---option\"quoted\"<<left>>");}finally{await fs.rm(directory,{recursive:true,force:true});}
});


it.each([
 ['  上传论文  ',false],
 ['   ',false],
 ['上传论文的语义分析',true],
])('prints only an actual thesis title, preserving the raw model (%j)',{timeout:120000},async(title,present)=>{
 const model=sample('en');model.reports[0].document.title=title;const before=JSON.stringify(model);
 const pdf=await renderReport({userId:'actual-title',report:{id:'report-1',source_filename:'论文.pdf',created_at:'2026-11-11T08:30:00Z'},model,format:'pdf'});
 expect(JSON.stringify(model)).toBe(before);
 const directory=await fs.mkdtemp(path.join(os.tmpdir(),'export-title-'));
 try{const file=path.join(directory,'report.pdf');await fs.writeFile(file,pdf.content);const text=execFileSync(process.env.REPORT_EXPORT_PDFTOTEXT||'/usr/bin/pdftotext',['-enc','UTF-8',file,'-'],{encoding:'utf8'});if(present){expect(text).toContain('Thesis title:');expect(text.replace(/\s/g,'')).toContain('上传论文的语义分析');}else expect(text).not.toContain('Thesis title:');}finally{await fs.rm(directory,{recursive:true,force:true});}
});


it('wraps a long ruleset hash inside the PDF body margins without losing characters',{timeout:120000},async()=>{
 const hash='858ba4587fd4d6a15e37cda456229d4627b067aff8b9ecae82381c8d2773aa151';
 const model=sample('en');model.reports[0].ruleset='Current local version · Reference checks '+hash;
 const pdf=await renderReport({userId:'ruleset-hash-margin',report:{id:'report-1',source_filename:'论文.pdf',created_at:'2026-11-11T08:30:00Z'},model,format:'pdf'});
 const directory=await fs.mkdtemp(path.join(os.tmpdir(),'export-hash-margin-'));
 try{const file=path.join(directory,'report.pdf');await fs.writeFile(file,pdf.content);const tool=process.env.REPORT_EXPORT_PDFTOTEXT||'/usr/bin/pdftotext';
  const text=execFileSync(tool,['-enc','UTF-8',file,'-'],{encoding:'utf8'});expect(text.replace(/\s/g,'')).toContain(hash);
  const bbox=execFileSync(tool,['-bbox',file,'-'],{encoding:'utf8'});const rightEdges=[...bbox.matchAll(/<word\b[^>]*\bxMax="([\d.]+)"/g)].map(match=>Number(match[1]));expect(rightEdges.length).toBeGreaterThan(0);expect(Math.max(...rightEdges)).toBeLessThanOrEqual(525);
 }finally{await fs.rm(directory,{recursive:true,force:true});}
});


it('wraps source titles after an unspaced translated opening quote inside PDF margins',{timeout:120000},async()=>{
 const model=sample('en');model.reports[0].findings[0].suggestions=[
  'Please insert a page break before“4benchmarkdesignandexperiments”',
  'Please insert a page break before‘4benchmarkdesignandexperiments’',
 ];
 const pdf=await renderReport({userId:'opening-quote-margin',report:{id:'report-1',source_filename:'论文.pdf',created_at:'2026-11-11T08:30:00Z'},model,format:'pdf'});
 const directory=await fs.mkdtemp(path.join(os.tmpdir(),'export-quote-margin-'));
 try{const file=path.join(directory,'report.pdf');await fs.writeFile(file,pdf.content);const tool=process.env.REPORT_EXPORT_PDFTOTEXT||'/usr/bin/pdftotext';
  const text=execFileSync(tool,['-enc','UTF-8',file,'-'],{encoding:'utf8'}).replace(/\s/g,'');expect(text).toContain('before“4benchmarkdesignandexperiments”');expect(text).toContain('before‘4benchmarkdesignandexperiments’');
  const bbox=execFileSync(tool,['-bbox',file,'-'],{encoding:'utf8'});const rightEdges=[...bbox.matchAll(/<word\b[^>]*\bxMax="([\d.]+)"/g)].map(match=>Number(match[1]));expect(rightEdges.length).toBeGreaterThan(0);expect(Math.max(...rightEdges)).toBeLessThanOrEqual(525);
 }finally{await fs.rm(directory,{recursive:true,force:true});}
});

it.each(['zh-CN','en'])('prints the official user-facing domain in the %s PDF footer, independent of the development host',{timeout:120000},async language=>{
 const model=sample(language);model.reports[0].signature={system:'System',institution:'Institution',website:'http://121.36.247.138:3000'};
 const pdf=await renderReport({userId:'canonical-domain',report:{id:'report-1',source_filename:'论文.pdf',created_at:'2026-11-11T08:30:00Z'},model,format:'pdf'});
 const directory=await fs.mkdtemp(path.join(os.tmpdir(),'export-domain-'));
 try{const file=path.join(directory,'report.pdf');await fs.writeFile(file,pdf.content);const text=execFileSync(process.env.REPORT_EXPORT_PDFTOTEXT||'/usr/bin/pdftotext',['-enc','UTF-8',file,'-'],{encoding:'utf8'});expect(text).toContain('https://thesis-review.sjtu.edu.cn');expect(text).not.toContain('121.36.247.138');}finally{await fs.rm(directory,{recursive:true,force:true});}
});
