import {beforeEach,afterEach,expect,it,vi} from 'vitest';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const {createTestDatabaseHarness}=require('../src/database/test_harness');
const {createArchiveScanService}=require('../src/normative/archiveScanService');
const harness=createTestDatabaseHarness({label:'combined-archive'});
const ids=['57aa0363-37ac-4ff5-b2c3-b9af12f444fe','4fc9290e-30c9-4d25-8034-2c491882b3e5','5996800a-a75b-4d05-8563-08004a647032'];
const groups=[[18,22,24,28],[11,13,14,15,16,29],[31,32,33]];
let db,base;
beforeEach(async()=>{
 db=await harness.setup();
 await db.run("INSERT INTO auth_users(id,username,password_hash,role,scope) VALUES('admin','admin','hash','SCHOOL_ADMIN','SCHOOL')");
 for(const [index,id] of ids.entries()){
  await db.run("INSERT INTO archive_scan_jobs(id,created_by,selected_rule_ids_json,status,total_count,completed_count,finding_count) VALUES(?,'admin',?,'completed',3,3,?)",[id,JSON.stringify(groups[index].map(n=>'sjtu_rule_'+n)),index===0?1:index===1?6:3]);
  for(const name of ['a','b','c']){
   const runs=groups[index].map(n=>{const count=n===24&&name==='a'?1:n===15?(name==='a'?2:name==='b'?3:0):n===11&&name==='b'?1:n===31?(name==='a'?1:name==='b'?2:0):0;
    return {rule_id:'sjtu_rule_'+n,outcome:count?'issues_found':'passed',findings:Array.from({length:count},(_,i)=>({finding_id:'f'+n+'_'+i,message:'issue',location:{page_number:1,text_excerpt:'source'}}))};});
   const finding_count=runs.reduce((n,r)=>n+r.findings.length,0);
   const result={rule_runs:runs,summary:{finding_count,rule_count:runs.length,completed_rule_count:runs.length,warning_finding_count:finding_count},...(index===0&&name==='a'?{finding_reviews:[{rule_id:'sjtu_rule_22',finding_id:'dismissed',disposition:'false_positive'}]}:{})};
   await db.run('INSERT INTO archive_scan_documents(id,job_id,relative_path,filename,size_bytes,status,finding_count,rule_outcomes_json,result_json) VALUES(?,?,?,?,?,?,?,?,?)',[index+'-'+name,id,'folder/'+name+'.pdf',name+'.pdf',100,'completed',finding_count,JSON.stringify(Object.fromEntries(runs.map(r=>[r.rule_id,r.outcome]))),JSON.stringify(result)]);
  }
 }
 base=createArchiveScanService();
});
afterEach(async()=>{await harness.cleanup();});
async function view(){return (await import('../src/normative/combinedArchiveService.js')).createCombinedArchiveService(base);}
it('shows one task, three unique papers, thirteen rules and per-rule distinct-paper counts',async()=>{
 const v=await view();const jobs=await v.listJobs();expect(jobs).toHaveLength(1);
 const job=jobs[0];expect(job.total_count).toBe(3);expect(job.completed_count).toBe(3);expect(job.finding_count).toBe(10);
 expect(job.selected_rule_ids).toHaveLength(13);expect(job.violating_paper_count).toBe(2);
 expect(job.rule_statistics.find(r=>r.rule_id==='sjtu_rule_15')).toMatchObject({finding_count:5,paper_count:2});
 expect(job.rule_statistics.find(r=>r.rule_id==='sjtu_rule_13')).toMatchObject({finding_count:0,paper_count:0});
 const filtered=await v.listDocuments(job.id,{ruleId:'sjtu_rule_31',query:'a.pdf'});
 expect(filtered.total).toBe(1);expect(filtered.finding_count).toBe(1);expect(filtered.violating_paper_count).toBe(1);
 expect(filtered.items[0].finding_count).toBe(1);
 const clean=await v.listDocuments(job.id,{ruleId:'sjtu_rule_31',outcome:'passed'});
 expect(clean.items.map(r=>r.filename)).toEqual(['c.pdf']);expect(clean.violating_paper_count).toBe(0);
});
it('merges the detail and preserves source IDs for every rule repair cache and PDF',async()=>{
 const v=await view();const job=(await v.listJobs())[0];const doc=await v.getDocument(job.id,'0-a');
 expect(doc.result.rule_runs).toHaveLength(13);expect(doc.finding_count).toBe(4);
 expect(doc.result.summary).toMatchObject({rule_count:13,completed_rule_count:13,finding_count:4,warning_finding_count:4});
 expect(doc.repair_sources.sjtu_rule_31).toEqual({job_id:ids[2],document_id:'2-a'});
 expect(doc.repair_sources.sjtu_rule_15).toEqual({job_id:ids[1],document_id:'1-a'});
 expect(doc.result.finding_reviews).toEqual([expect.objectContaining({disposition:'false_positive'})]);
 base.archivePdfPath=vi.fn().mockResolvedValue('/safe/a.pdf');
 expect(await v.archivePdfPath(job.id,'0-a')).toBe('/safe/a.pdf');expect(base.archivePdfPath).toHaveBeenCalledWith(ids[0],'0-a');
 expect(await db.get('select count(*) n from archive_scan_jobs')).toEqual({n:3});
 await expect(v.deleteJob(job.id)).rejects.toMatchObject({status:409});
 await expect(v.getDocument(job.id,'missing')).rejects.toMatchObject({status:404});
});
it('keeps partial or mismatched scan sets separate instead of inventing completed checks',async()=>{
 await db.run('DELETE FROM archive_scan_documents WHERE id=?',['2-c']);
 expect(await (await view()).listJobs()).toHaveLength(3);
});
