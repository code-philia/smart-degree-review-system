import { createRequire } from 'node:module';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import bcrypt from 'bcrypt';
import request from 'supertest';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

const require = createRequire(import.meta.url);
const app = require('../src/app');
const db = require('../src/database');
const reports = require('../src/normative/paperLintReportRepository');
const { trialAttempts } = require('../src/auth/trialLoginPolicy');
const { supervisionAttempts } = require('../src/auth/supervisionPolicy');
const harness = db.createTestDatabaseHarness({ label: 'supervision', seedDefault: true });
const password = 'supervision-fixture-only';
const origin = 'http://review.example.test';
const envKeys = ['NODE_ENV','ARC_AUTH_MODE','APP_PUBLIC_URL','ARC_TRIAL_LOGIN_ENABLED','ARC_TRIAL_LOGIN_ORIGINS','PAPER_LINT_REPORTS_DIR','ARC_QPDF_BINARY'];
let oldEnv, directory;
const auth = (method, url, cookie = 'supervision:fixture') => request(app)[method](url)
  .set('Host','review.example.test').set('Origin',origin).set('Cookie','arc_session='+cookie);
const login = (input = { username:'admin',password }) => request(app).post('/api/auth/supervision-login')
  .set('Host','review.example.test').set('Origin',origin).send(input);

beforeEach(async () => {
  oldEnv=Object.fromEntries(envKeys.map(k=>[k,process.env[k]]));
  directory=await fs.mkdtemp(path.join(os.tmpdir(),'supervision-test-'));
  Object.assign(process.env,{NODE_ENV:'production',ARC_AUTH_MODE:'jaccount-only',APP_PUBLIC_URL:origin,
    ARC_TRIAL_LOGIN_ENABLED:'1',ARC_TRIAL_LOGIN_ORIGINS:origin,PAPER_LINT_REPORTS_DIR:directory,ARC_QPDF_BINARY:'missing-supervision-test-qpdf'});
  trialAttempts.clear();
  supervisionAttempts.clear();
  await harness.setup();
  const hash=await bcrypt.hash(password,4);
  await db.run('UPDATE auth_users SET password_hash=?',[hash]);
  await db.run("INSERT INTO auth_users(id,username,display_name,password_hash,role,scope) VALUES ('admin','admin','管理员',?,'SCHOOL_ADMIN','SCHOOL')",[hash]);
  await db.run("UPDATE auth_users SET display_name='学生甲' WHERE id='student01'");
  for(const [id,user] of [['supervision:fixture','admin'],['supervision:student','student01'],['private:admin','school_admin01'],['trial:school','school_admin01']])
    await db.run("INSERT INTO auth_sessions(id,user_id,expires_at) VALUES (?,?,'2099-01-01T00:00:00.000Z')",[id,user]);
  for(const [id,user,name,date] of [['report-a','student01','论文甲.pdf','2026-11-23T10:00:00.000Z'],['report-b','supervisor01','论文乙.pdf','2026-11-24T10:00:00.000Z']]){
    await reports.createPaperLintReport({reportId:id,userId:user,sourceFilename:name,pdfBuffer:Buffer.from('%PDF-1.7\nfixture'),selectedRuleIds:['sjtu_rule_15'],result:{type:'paper_lint',paper_title:name,ruleset:{id:'test',version_label:'test'},rule_runs:[{rule_id:'sjtu_rule_15',severity:'warning',execution_status:'completed',outcome:'issues_found',findings:[{finding_id:'f1',message:'测试告警原文',suggestion:'保存的建议'}]}]}});
    await db.run('UPDATE paper_lint_reports SET created_at=? WHERE id=?',[date,id]);
  }
  await db.run("INSERT INTO system_feedback(id,user_id,satisfaction_score,improvement_areas_json,comment) VALUES ('sys','student01',2,'[\"detection_accuracy\"]','<script>原始用户反馈</script>')");
  await db.run("INSERT INTO paper_lint_finding_feedback(id,user_id,report_id,rule_id,finding_id,feedback_value,reason_code,reason_text) VALUES ('finding-no','student01','report-a','sjtu_rule_15','f1','negative','false_positive','这条是误报'),('finding-yes','supervisor01','report-b','sjtu_rule_15','f1','positive',NULL,NULL)");
  await db.run(`INSERT INTO paper_lint_repair_suggestions(id,report_id,user_id,document_sha256,rule_id,finding_id,context_sha256,generation,status,provider,model,model_version,prompt_version,response_json)
    VALUES ('suggestion','report-a','student01','sha','sjtu_rule_15','f1','ctx',1,'suggested','test','test','v1','p1','{"actions":[]}')`);
  await db.run("INSERT INTO paper_lint_suggestion_feedback(id,user_id,report_id,rule_id,finding_id,suggestion_id,generation,feedback_value,reason_code,reason_text) VALUES ('suggestion-no','student01','report-a','sjtu_rule_15','f1','suggestion',1,'negative','insufficient_basis','依据不足')");
});
afterEach(async()=>{
  await harness.cleanup();
  await fs.rm(directory,{recursive:true,force:true});
  for(const [k,v] of Object.entries(oldEnv)){if(v===undefined)delete process.env[k];else process.env[k]=v;}
});

describe('owner supervision access',()=>{
  it('starts a dedicated read-only session and restores its administrator identity',async()=>{
    const response=await login().expect(200);
    expect(response.body.user).toMatchObject({id:'admin',username:'admin',role:'SCHOOL_ADMIN',accessMode:'supervision'});
    const cookie=response.headers['set-cookie'].find(c=>c.startsWith('arc_session=')).split(';')[0];
    expect(decodeURIComponent(cookie)).toMatch(/^arc_session=supervision:/);
    expect(response.headers['set-cookie'].join(';')).toMatch(/HttpOnly/);
    await request(app).get('/api/auth/me').set('Cookie',cookie).expect(200).expect(({body})=>expect(body.user.accessMode).toBe('supervision'));
    await request(app).post('/api/auth/logout').set('Cookie',cookie).expect(204);
    await request(app).get('/api/auth/me').set('Cookie',cookie).expect(401);
  });
  it('does not authenticate another local account through the supervision login',async()=>{
    await login({username:'school_admin01',password}).expect(401);
    await login({username:'admin',password:'wrong'}).expect(401);
    await login({username:['admin'],password}).expect(401);
  });
  it.each([['https://attacker.example','review.example.test'],[origin,'attacker.example']])('rejects mismatched browser origin %s / %s',async(originHeader,host)=>{
    await request(app).post('/api/auth/supervision-login').set('Origin',originHeader).set('Host',host).send({username:'admin',password}).expect(403);
  });
  it('bounds repeated password attempts',async()=>{
    for(let i=0;i<5;i++)await login({username:'admin',password:'wrong'}).expect(401);
    const limited=await login().expect(429);expect(limited.headers['retry-after']).toBeTruthy();
  });
  it('does not consume trial login budget when console passwords fail',async()=>{
    for(let i=0;i<20;i++)await login({username:'unknown-'+i,password:'wrong'}).expect(401);
    await request(app).post('/api/auth/trial-login').set('Host','review.example.test').set('Origin',origin)
      .send({username:'student01',password}).expect(200);
  });
  it.each(['','supervision:student','private:admin','trial:school','supervision:forged'])('rejects a non-supervision identity %s',async(cookie)=>{
    const response=await auth('get','/api/supervision/summary',cookie);expect([401,403]).toContain(response.status);
  });
  it('counts all reports and every feedback category',async()=>{
    await auth('get','/api/supervision/summary').expect(200).expect(({body})=>expect(body).toMatchObject({users:5,reports:2,feedback:4,negative_feedback:3}));
  });
  it('includes legacy reports, keeps types distinct and only reads saved results',async()=>{
    await db.run("INSERT INTO normative_detection_tasks(id,user_id,status,source_type,original_text,rule_snapshot_json,issues_json,severity_counts_json) VALUES ('report-a','student01','completed','paste','历史原文','[]','[{\"message\":\"历史问题\"}]','{}')");
    await db.run("INSERT INTO duplication_detection_reports(id,user_id,source_type,original_text,total_similarity_rate,writing_risk_score,sample_count,report_json) VALUES ('legacy-dup','supervisor01','paste','检测原文',12.5,20,1,'{\"summary\":\"已保存结果\"}')");
    await db.run("INSERT INTO example_rule_reports(id,user_id,source_filename,source_pdf_path,rule_snapshots_json,result_json) VALUES ('legacy-example','student01','示例.pdf','/missing/test.pdf','[]','{\"findings\":[]}')");
    await auth('get','/api/supervision/summary').expect(200).expect(({body})=>expect(body.reports).toBe(5));
    await auth('get','/api/supervision/reports').expect(200).expect(({body})=>{expect(body.total).toBe(5);expect(new Set(body.items.map(r=>r.report_type))).toEqual(new Set(['paper_lint','normative','duplication','example']));});
    await auth('get','/api/supervision/reports?type=normative').expect(200).expect(({body})=>expect(body.items[0]).toMatchObject({id:'report-a',report_type:'normative'}));
    await auth('get','/api/supervision/reports/report-a?type=normative').expect(200).expect(({body})=>expect(body.legacy).toMatchObject({original_text:'历史原文',saved_result:{issues:[{message:'历史问题'}]}}));
    await auth('get','/api/supervision/reports/legacy-dup?type=duplication').expect(200).expect(({body})=>{expect(body.legacy.saved_result.summary).toBe('已保存结果');expect(JSON.stringify(body)).not.toContain('password_hash');});
    await auth('get','/api/supervision/reports/legacy-example?type=example').expect(200);
    await auth('get','/api/supervision/reports/legacy-example/pdf?type=example').expect(410);
    await auth('get','/api/supervision/reports?type=unknown').expect(400);
    await auth('get','/api/supervision/reports/report-a?type=unknown').expect(400);
  });
  it('lists other users reports with stable server pagination and owner names',async()=>{
    const first=await auth('get','/api/supervision/reports?page_size=1&page=1').expect(200);
    expect(first.body).toMatchObject({total:2,page:1,page_size:1});
    expect(first.body.items[0]).toMatchObject({id:'report-b',owner:{username:'supervisor01'}});
    const second=await auth('get','/api/supervision/reports?page_size=1&page=2').expect(200);
    expect(second.body.items[0]).toMatchObject({id:'report-a',owner:{display_name:'学生甲'}});
    expect(JSON.stringify(first.body)).not.toContain('source_pdf_path');
    expect(JSON.stringify(first.body)).not.toContain('password_hash');
  });
  it('searches filenames and users, treating SQL-like input as literal text',async()=>{
    await auth('get','/api/supervision/reports?search_field=display_name&q='+encodeURIComponent('学生甲')).expect(200).expect(({body})=>expect(body.items.map(r=>r.id)).toEqual(['report-a']));
    await auth('get','/api/supervision/reports?q='+encodeURIComponent("' OR 1=1 --")).expect(200).expect(({body})=>expect(body.total).toBe(0));
    await auth('get','/api/supervision/reports?search_field=filename&q='+encodeURIComponent('学生甲')).expect(200).expect(({body})=>expect(body.total).toBe(0));
    await auth('get','/api/supervision/reports?search_field=unknown').expect(400);
    await auth('get','/api/supervision/feedback?search_field=unknown').expect(400);
    await auth('get','/api/supervision/feedback?search_field=content&q='+encodeURIComponent('误报')).expect(200).expect(({body})=>expect(body.total).toBe(1));
    await auth('get','/api/supervision/feedback?search_field=filename&q='+encodeURIComponent('误报')).expect(200).expect(({body})=>expect(body.total).toBe(0));
    await auth('get','/api/supervision/reports?user_id=student01').expect(200).expect(({body})=>expect(body.total).toBe(1));
  });
  it.each(['page=0','page=NaN','page_size=10000','type=unknown','value=unknown'])('rejects malformed filters %s',async(query)=>{
    await auth('get','/api/supervision/'+(query.startsWith('type')||query.startsWith('value')?'feedback':'reports')+'?'+query).expect(400);
  });
  it('reads another user report and its private PDF without changing ownership rules',async()=>{
    await auth('get','/api/supervision/reports/report-a').expect(200).expect(({body})=>{
      expect(body.report.id).toBe('report-a');expect(body.owner.username).toBe('student01');
      expect(body.report.result.rule_runs[0].findings[0].message).toBe('测试告警原文');
    });
    await auth('get','/api/supervision/reports/report-a/pdf').expect(200).expect('Content-Type',/application\/pdf/);
    await auth('get','/api/supervision/reports/missing').expect(404);
    await auth('get','/api/supervision/reports/missing/pdf').expect(404);
    await fs.unlink(path.join(directory,'report-a.pdf'));
    await auth('get','/api/supervision/reports/report-a/pdf').expect(410);
  });
  it('returns all feedback, its reasons and report context with useful filters',async()=>{
    const response=await auth('get','/api/supervision/feedback').expect(200);
    expect(response.body.total).toBe(4);expect(new Set(response.body.items.map(r=>r.type))).toEqual(new Set(['system','finding','suggestion']));
    expect(response.body.items.find(r=>r.id==='finding-no')).toMatchObject({reason_label:'误报',finding_text:'测试告警原文',report_id:'report-a'});
    expect(response.body.items.find(r=>r.type==='system').comment).toBe('<script>原始用户反馈</script>');
    await auth('get','/api/supervision/feedback?type=finding&value=negative').expect(200).expect(({body})=>expect(body.items.map(r=>r.id)).toEqual(['finding-no']));
    await auth('get','/api/supervision/feedback?value=negative').expect(200).expect(({body})=>expect(body.total).toBe(3));
  });
  it.each([
    ['post','/api/normative/paper-lint/run'],['delete','/api/normative/paper-lint/reports/report-a'],
    ['post','/api/normative/paper-lint/reports/report-a/rerun'],['post','/api/normative/feedback/system-feedback'],
    ['put','/api/normative/feedback/reports/report-a/findings/sjtu_rule_15/f1/feedback'],['get','/api/normative/paper-lint/reports'],
    ['post','/api/normative/paper-lint/control/rollback'],['put','/api/auth/notification-settings'],
  ])('does not grant ordinary application access: %s %s',async(method,url)=>{
    await auth(method,url).send({}).expect(403);
    expect((await db.get('SELECT count(*) AS n FROM paper_lint_reports')).n).toBe(2);
  });
});
