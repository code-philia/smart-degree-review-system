import { afterEach, beforeEach, expect, it } from 'vitest';
import { createRequire } from 'node:module';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {createHash} from 'node:crypto';
const require = createRequire(import.meta.url);
const {createTestDatabaseHarness}=require('../src/database/test_harness');
let root,harness,db,uploads;
beforeEach(async()=>{
  root=await fs.mkdtemp(path.join(os.tmpdir(),'admin-export-test-'));
  harness=createTestDatabaseHarness({dbPath:path.join(root,'test.db')}); db=await harness.setup();
  uploads=path.join(root,'uploads');await fs.mkdir(uploads);
  for(const id of ['a','b']) {
    await db.run('INSERT INTO auth_users (id,username,password_hash,role,scope) VALUES (?,?,?, ?,?)',[id,id,'PRIVATE_PASSWORD','STUDENT','COLLEGE']);
    await fs.writeFile(path.join(uploads,id+'.pdf'),'%PDF-1.7 '+id);
    await db.run('INSERT INTO paper_lint_reports (id,user_id,source_filename,source_pdf_path,selected_rule_ids_json,result_json) VALUES (?,?,?,?,?,?)',[id,id,'../../论文'+id+'.pdf',path.join(uploads,id+'.pdf'),'[]',JSON.stringify({rule_runs:[{rule_id:'test',status:'completed',findings:[{severity:'warning',message:'示例结果'}]}]})]);
  }
});
afterEach(async()=>{await harness.cleanup();await fs.rm(root,{recursive:true,force:true});});
it('exports every user report and original PDF privately, with an index and readable report',async()=>{
 const {exportAllReports}=require('../src/normative/adminDataExport');
 const result=await exportAllReports({database:db,dbPath:harness.dbPath,uploadsDir:uploads});
 expect(result.report_count).toBe(2);expect(result.pdf_count).toBe(2);
 const index=JSON.parse(await fs.readFile(path.join(result.directory,'index.json'),'utf8'));
 expect(index.records.map(r=>r.username)).toEqual(['a','b']);
 for(const r of index.records){
  expect((await fs.readFile(path.join(result.directory,r.pdf_file),'utf8')).startsWith('%PDF-1.7')).toBe(true);
  const raw=await fs.readFile(path.join(result.directory,r.report_file),'utf8');
  expect(raw).toContain('示例结果');expect(raw).not.toContain('PRIVATE_PASSWORD');
  expect(await fs.readFile(path.join(result.directory,r.readable_file),'utf8')).toContain('示例结果');
  expect((await fs.stat(path.join(result.directory,r.pdf_file))).mode & 0o077).toBe(0);
 }
 expect((await fs.stat(result.directory)).mode & 0o077).toBe(0);
 expect(JSON.parse(await fs.readFile(path.join(root,'admin-export/latest.json'),'utf8')).snapshot).toBe(path.basename(result.directory));
 expect(await db.all('SELECT id FROM paper_lint_reports')).toHaveLength(2);
});
it('reports missing or out-of-root PDFs explicitly, without copying an arbitrary backend file',async()=>{
 const secret=path.join(root,'secret.txt');await fs.writeFile(secret,'PRIVATE_SECRET');
 await db.run("UPDATE paper_lint_reports SET source_pdf_path=? WHERE id='a'",[secret]);
 await fs.unlink(path.join(uploads,'b.pdf'));
 const {exportAllReports}=require('../src/normative/adminDataExport');
 const r=await exportAllReports({database:db,dbPath:harness.dbPath,uploadsDir:uploads});
 expect(r.pdf_count).toBe(0);
 const index=JSON.parse(await fs.readFile(path.join(r.directory,'index.json'),'utf8'));
 expect(index.records.map(x=>x.pdf_status).sort()).toEqual(['missing','outside_upload_root']);
 expect(index.records.every(x=>x.pdf_file===null)).toBe(true);
});
it('supports a no-copy index export and never reuses stale snapshot files',async()=>{
 const {exportAllReports}=require('../src/normative/adminDataExport');
 const r=await exportAllReports({database:db,dbPath:harness.dbPath,uploadsDir:uploads,indexOnly:true});
 expect(r.report_count).toBe(2);expect(r.pdf_count).toBe(0);
 const r2=await exportAllReports({database:db,dbPath:harness.dbPath,uploadsDir:uploads});
 expect(r2.directory).not.toBe(r.directory);expect(r2.pdf_count).toBe(2);
});

it('uses the configured upload directory from the real maintenance command',async()=>{
 const previous=process.env.PAPER_LINT_REPORTS_DIR;process.env.PAPER_LINT_REPORTS_DIR=uploads;
 try {
  const r=await require('../src/normative/adminDataExport').exportAllReports({database:db,dbPath:harness.dbPath});
  expect(r.pdf_count).toBe(2);
 } finally {if(previous===undefined)delete process.env.PAPER_LINT_REPORTS_DIR;else process.env.PAPER_LINT_REPORTS_DIR=previous;}
});

it('runs the actual maintenance CLI read-only against existing data',async()=>{
 const before=createHash('sha256').update(await fs.readFile(harness.dbPath)).digest('hex');
 const cmd=path.resolve('src/adminExport.js');
 const env={...process.env,ARC_DB_FILE:harness.dbPath,PAPER_LINT_REPORTS_DIR:uploads};
 const reports=await promisify(execFile)(process.execPath,[cmd,'reports'],{env});
 expect(JSON.parse(reports.stdout).pdf_count).toBe(2);
 const feedback=await promisify(execFile)(process.execPath,[cmd,'feedback'],{env});
 expect(JSON.parse(feedback.stdout).count).toBe(0);
 const after=createHash('sha256').update(await fs.readFile(harness.dbPath)).digest('hex');
 expect(after).toBe(before);
 await expect(promisify(execFile)(process.execPath,[cmd,'reports','--unknown'],{env})).rejects.toMatchObject({code:1});
});

it('includes an explicitly configured legacy upload root',async()=>{
 const legacy=path.join(root,'legacy');await fs.mkdir(legacy);
 const file=path.join(legacy,'old.pdf');await fs.writeFile(file,'%PDF-1.7 legacy');
 await db.run("UPDATE paper_lint_reports SET source_pdf_path=? WHERE id='a'",[file]);
 const previous=process.env.ADMIN_EXPORT_PDF_ROOTS;process.env.ADMIN_EXPORT_PDF_ROOTS=legacy;
 try {
  const r=await require('../src/normative/adminDataExport').exportAllReports({database:db,dbPath:harness.dbPath,uploadsDir:uploads});
  expect(r.pdf_count).toBe(2);
 }finally{if(previous===undefined)delete process.env.ADMIN_EXPORT_PDF_ROOTS;else process.env.ADMIN_EXPORT_PDF_ROOTS=previous;}
});
