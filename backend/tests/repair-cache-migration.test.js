import {expect,it} from 'vitest';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const sqlite3=require('sqlite3');const {ensureArchiveRepairSchema}=require('../src/database/repairSuggestionSchema');
const run=(db,sql,params=[])=>new Promise((resolve,reject)=>db.run(sql,params,error=>error?reject(error):resolve()));
const all=(db,sql)=>new Promise((resolve,reject)=>db.all(sql,(error,rows)=>error?reject(error):resolve(rows)));
it('upgrades the deployed unique cache without losing old rows, then supports multiple generations and repeated startup',async()=>{
 const db=new sqlite3.Database(':memory:');
 try{
  await run(db,`CREATE TABLE repair_suggestions(id TEXT PRIMARY KEY,source_kind TEXT,job_id TEXT,document_id TEXT,document_sha256 TEXT,detector_version TEXT,rule_id TEXT,finding_id TEXT,context_sha256 TEXT,status TEXT,provider TEXT,model TEXT,model_version TEXT,prompt_version TEXT,response_json TEXT,created_at TEXT,UNIQUE(job_id,document_id,rule_id,finding_id,context_sha256,model,model_version,prompt_version))`);
  const values=['old','legacy_archive','job','doc','sha','v','sjtu_rule_31','f','context','suggested','huawei_maas','m','v','p','{"original":true}','2026-10-19'];
  await run(db,'INSERT INTO repair_suggestions VALUES('+values.map(()=>'?').join(',')+')',values);
  await ensureArchiveRepairSchema(db);await ensureArchiveRepairSchema(db);
  const before=(await all(db,'SELECT * FROM repair_suggestions'))[0];expect(before.generation).toBe(1);expect(before.id).toBe('old');expect(before.response_json).toBe('{"original":true}');expect(before.created_at).toBe('2026-10-19');
  await run(db,`INSERT INTO repair_suggestions SELECT 'new',source_kind,job_id,document_id,document_sha256,detector_version,rule_id,finding_id,context_sha256,2,status,provider,model,model_version,prompt_version,'{"new":true}',created_at FROM repair_suggestions WHERE id='old'`);
  expect((await all(db,'SELECT id FROM repair_suggestions ORDER BY generation DESC')).map(x=>x.id)).toEqual(['new','old']);
  expect(await all(db,'PRAGMA foreign_key_check')).toEqual([]);
 }finally{await new Promise(resolve=>db.close(resolve));}
});
