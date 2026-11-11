import fs from 'node:fs';import os from 'node:os';import path from 'node:path';import {createRequire}from'node:module';import{expect,it}from'vitest';
const require=createRequire(import.meta.url);
const {getDbPath,setDbPath,getDb,initializeDatabase,closeDb,get,run}=require('../src/database');
it('preserves existing accounts and opts old completed or pending jobs out of email during migration',async()=>{
  const previous=getDbPath();const directory=fs.mkdtempSync(path.join(os.tmpdir(),'report-email-migration-'));
  try{
    await setDbPath(path.join(directory,'existing.sqlite'));
    await new Promise((resolve,reject)=>getDb().exec(`
      CREATE TABLE auth_users(id TEXT PRIMARY KEY,username TEXT NOT NULL UNIQUE,password_hash TEXT NOT NULL,role TEXT NOT NULL,college_id TEXT,supervisor_id TEXT,scope TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
      INSERT INTO auth_users(id,username,password_hash,role,scope) VALUES('old-user','old-user','existing-hash','STUDENT','COLLEGE');
      CREATE TABLE paper_lint_reports(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,source_filename TEXT NOT NULL,source_pdf_path TEXT NOT NULL,selected_rule_ids_json TEXT NOT NULL,result_json TEXT NOT NULL,created_at TEXT NOT NULL);
      INSERT INTO paper_lint_reports VALUES('old-report','old-user','paper.pdf','paper.pdf','[]','{}','2026-11-06');
      CREATE TABLE paper_lint_jobs(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,source_filename TEXT NOT NULL,source_pdf_path TEXT NOT NULL,selected_rule_ids_json TEXT NOT NULL,external_consent INTEGER DEFAULT 0,status TEXT NOT NULL,attempts INTEGER DEFAULT 0,report_id TEXT,error_message TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
      INSERT INTO paper_lint_jobs(id,user_id,source_filename,source_pdf_path,selected_rule_ids_json,status,created_at,updated_at) VALUES('old-completed','old-user','paper.pdf','paper.pdf','[]','completed','2026-11-06','2026-11-06'),('old-pending','old-user','paper.pdf','paper.pdf','[]','pending','2026-11-06','2026-11-06');
    `,error=>error?reject(error):resolve()));
    await initializeDatabase();
    expect(await get("SELECT username,password_hash,email FROM auth_users WHERE id='old-user'")).toEqual({username:'old-user',password_hash:'existing-hash',email:null});
    expect((await get("SELECT notify_completion FROM paper_lint_jobs WHERE id='old-completed'")).notify_completion).toBe(0);
    expect((await get("SELECT notification_locale FROM paper_lint_jobs WHERE id='old-completed'")).notification_locale).toBe('zh');
    await run("UPDATE paper_lint_jobs SET notification_locale='en' WHERE id='old-pending'");
    const jobs=require('../src/normative/paperLintJobRepository');await jobs.claimJob('old-pending');await jobs.completeJob('old-pending','old-report');
    expect((await get('SELECT count(*) AS total FROM report_email_outbox')).total).toBe(0);
    await closeDb();await initializeDatabase();
    expect((await get("SELECT notify_completion FROM paper_lint_jobs WHERE id='old-pending'")).notify_completion).toBe(0);
    expect((await get("SELECT notification_locale FROM paper_lint_jobs WHERE id='old-pending'")).notification_locale).toBe('en');
  }finally{await closeDb();await setDbPath(previous);fs.rmSync(directory,{recursive:true,force:true});}
});
