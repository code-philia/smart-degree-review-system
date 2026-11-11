import { beforeAll, afterAll, beforeEach, expect, it } from 'vitest';
import { createRequire } from 'node:module';
import fs from 'node:fs'; import os from 'node:os'; import path from 'node:path';
const require = createRequire(import.meta.url);
const { createTestDatabaseHarness, get, run } = require('../src/database');
const jobs = require('../src/normative/paperLintJobRepository');
const reports = require('../src/normative/paperLintReportRepository');
let harness, directory, clock;
const settings = { origin:'https://review.example.test', from:'sender@example.test', fromName:'学位检测系统' };
const result = { type:'paper_lint', rule_runs:[{rule_id:'r1',severity:'warning',execution_status:'completed',outcome:'issues_found',findings:[{rule_id:'r1',finding_id:'one',message:'示例问题'}]},
  {rule_id:'r2',severity:'info',execution_status:'unsupported',outcome:'inconclusive',message:'未能检测：缺少参考文献。',findings:[]}],summary:{} };
async function completed(userId='mail-user', filename='论文.pdf') {
  const pdf=Buffer.from('%PDF-1.7\nmail');
  const id=await jobs.createJob({userId,sourceFilename:filename,pdfBuffer:pdf,selectedRuleIds:['r1','r2']});
  await jobs.claimJob(id); await reports.createPaperLintReport({userId,sourceFilename:filename,pdfBuffer:pdf,selectedRuleIds:['r1','r2'],result,reportId:id});
  await jobs.completeJob(id,id); return id;
}
beforeAll(async()=>{
  directory=fs.mkdtempSync(path.join(os.tmpdir(),'mail-worker-'));
  process.env.PAPER_LINT_JOBS_DIR=path.join(directory,'jobs');process.env.PAPER_LINT_REPORTS_DIR=path.join(directory,'reports');
  harness=createTestDatabaseHarness({label:'mail-worker',seedDefault:true});await harness.setup();
  await run("INSERT INTO auth_users(id,username,password_hash,role,scope) SELECT 'mail-user','mail-user',password_hash,'STUDENT','COLLEGE' FROM auth_users WHERE id='student01'");
  await run('UPDATE auth_users SET email=? WHERE id=?',['person@example.test','mail-user']);
});
beforeEach(async()=>{clock=Date.now()+1000;await run('DELETE FROM report_email_outbox');});
afterAll(async()=>{await harness.cleanup();fs.rmSync(directory,{recursive:true,force:true});delete process.env.PAPER_LINT_JOBS_DIR;delete process.env.PAPER_LINT_REPORTS_DIR;});
function worker(send, config=()=>settings) {
  return require('../src/notifications/reportEmailService').createReportEmailService({send,config,now:()=>clock});
}
it('sends one bilingual report-ready notice with language-specific protected report links',async()=>{
  const id=await completed();const sent=[];await worker(async mail=>sent.push(mail)).drain();
  expect(sent).toHaveLength(1); const mail=sent[0];
  expect(mail.to).toBe('person@example.test');expect(mail.text).toContain('您的论文检测报告已生成');
  expect(mail.text).toContain('Your thesis report is ready.');
  expect(mail.html).toContain('https://review.example.test/reports/pdf/'+id+'?lang=zh');
  expect(mail.html).toContain('https://review.example.test/reports/pdf/'+id+'?lang=en');
  expect(mail.attachments).toBeUndefined();expect((await get('SELECT status FROM report_email_outbox WHERE job_id=?',[id])).status).toBe('sent');
});
it.each(['student01','supervisor01','school_admin01','college_admin01'])('sends %s only to the fixed destination',async user=>{
  await run('UPDATE auth_users SET email=? WHERE id=?',['wrong@example.test',user]);await completed(user);
  const sent=[];await worker(async mail=>sent.push(mail)).drain();expect(sent.map(mail=>mail.to)).toEqual(['123090058@link.cuhk.edu.cn']);
});
it('does not consume attempts while SMTP is unconfigured',async()=>{
  const id=await completed();await worker(async()=>{throw Error('must not send');},()=>null).drain();
  expect(await get('SELECT status,attempts FROM report_email_outbox WHERE job_id=?',[id])).toEqual({status:'pending',attempts:0});
});
it('retries a failed SMTP delivery independently of the completed detection',async()=>{
  const id=await completed();let attempts=0;const sent=[];
  const service=worker(async mail=>{attempts++;if(attempts===1)throw Object.assign(Error('secret smtp response'),{code:'ECONNECTION'});sent.push(mail);});
  await service.drain();expect((await jobs.getJob(id)).status).toBe('completed');
  let row=await get('SELECT * FROM report_email_outbox WHERE job_id=?',[id]);expect(row).toMatchObject({status:'pending',attempts:1,error_code:'smtp_unavailable'});
  expect(JSON.stringify(row)).not.toContain('secret smtp response');
  await service.drain();expect(attempts).toBe(1);
  clock=Date.parse(row.next_attempt_at)+1;await service.drain();
  expect(sent).toHaveLength(1);expect((await get('SELECT status FROM report_email_outbox WHERE job_id=?',[id])).status).toBe('sent');
});
it('limits retries and leaves the report available after persistent SMTP failure',async()=>{
  const id=await completed();let count=0;const service=worker(async()=>{count++;throw Error('offline');});
  for(let i=0;i<6;i++){await service.drain();clock+=24*60*60*1000;}
  expect(count).toBe(5);expect((await get('SELECT status FROM report_email_outbox WHERE job_id=?',[id])).status).toBe('failed');
  expect(await reports.findPaperLintReportByIdForUser(id,'mail-user')).toBeTruthy();
});
it('recovers an expired lease and uses the same stable Message-ID',async()=>{
  const id=await completed();await run("UPDATE report_email_outbox SET status='sending',attempts=1,lease_until=?,claim_token='old' WHERE job_id=?",[new Date(clock-1000).toISOString(),id]);
  const sent=[];await worker(async mail=>sent.push(mail)).drain();await worker(async mail=>sent.push(mail)).drain();
  expect(sent).toHaveLength(1);expect(sent[0].messageId).toBe(`<report-${id}@example.test>`);
});
it('allows only one worker to send a claimed notification',async()=>{
  await completed();const sent=[];let release;const block=new Promise(resolve=>{release=resolve;});
  const one=worker(async mail=>{sent.push(mail);await block;});const two=worker(async mail=>sent.push(mail));
  const first=one.drain();for(let i=0;i<50&&!sent.length;i++)await new Promise(resolve=>setTimeout(resolve,5));
  await two.drain();release();await first;expect(sent).toHaveLength(1);
});
it('does not send mail after the saved report has been deleted',async()=>{
  const id=await completed();await reports.deletePaperLintReportForUser(id,'mail-user');const sent=[];
  await worker(async mail=>sent.push(mail)).drain();expect(sent).toHaveLength(0);
});
it('escapes untrusted filenames in HTML and strips subject header injection',async()=>{
  await completed('mail-user','<img src=x onerror=alert(1)>\r\nBcc: victim@example.test.pdf');
  const sent=[];await worker(async mail=>sent.push(mail)).drain();
  expect(sent[0].subject).not.toMatch(/[\r\n]/);expect(sent[0].html).not.toContain('<img');expect(sent[0].html).toContain('&lt;img');
});
it('blocks a missing recipient until the user supplies a mailbox',async()=>{
  await run('UPDATE auth_users SET email=NULL WHERE id=?',['mail-user']);const id=await completed();const sent=[];
  await worker(async mail=>sent.push(mail)).drain();expect(sent).toHaveLength(0);
  expect(await get('SELECT status,error_code FROM report_email_outbox WHERE job_id=?',[id])).toEqual({status:'blocked',error_code:'missing_recipient'});
  await run('UPDATE auth_users SET email=? WHERE id=?',['person@example.test','mail-user']);
  await worker(async mail=>sent.push(mail)).drain();expect(sent).toHaveLength(1);
});
it('keeps old queued notifications untouched while delivering jobs after activation',async()=>{
  const old=await completed(),recent=await completed();
  await run('UPDATE report_email_outbox SET created_at=? WHERE job_id=?',['2026-11-10T23:59:59.000Z',old]);
  await run('UPDATE report_email_outbox SET created_at=? WHERE job_id=?',['2026-11-11T00:00:00.000Z',recent]);
  const sent=[];await worker(async mail=>sent.push(mail),()=>({...settings,notBefore:'2026-11-11T00:00:00.000Z'})).drain();
  expect(sent.map(mail=>mail.messageId)).toEqual([`<report-${recent}@example.test>`]);
  expect(await get('SELECT status,attempts FROM report_email_outbox WHERE job_id=?',[old])).toEqual({status:'pending',attempts:0});
});
it('delivers through the configured campus API provider using the normal outbox worker',async()=>{
  const id=await completed('student01');const originalFetch=globalThis.fetch;const calls=[];
  globalThis.fetch=async(url,opts)=>{calls.push({url,opts});return new Response(JSON.stringify(url.endsWith('/token')
    ?{access_token:'worker-token',token_type:'Bearer',expires_in:1800}
    :{errno:0,error:'success',total:0,entities:[{id,emails:['123090058@link.cuhk.edu.cn'],channels:['email']}]}),{status:200});};
  try {
    const apiSettings={...settings,provider:'sjtu-notification',clientId:'outbox-app',clientSecret:'test-app-secret',username:'sender',password:'test-sender-secret'};
    await require('../src/notifications/reportEmailService').createReportEmailService({config:()=>apiSettings,now:()=>clock}).drain();
    expect((await get('SELECT status FROM report_email_outbox WHERE job_id=?',[id])).status).toBe('sent');
    expect(calls).toHaveLength(2);expect(JSON.parse(calls[1].opts.body).emails).toEqual(['123090058@link.cuhk.edu.cn']);
    expect(JSON.parse(calls[1].opts.body).content).toContain('/reports/pdf/'+id);
  } finally {globalThis.fetch=originalFetch;}
});
it('sends immediately after commit without waiting for a poll or delaying the completed report',async()=>{
  let began,release;const started=new Promise(resolve=>{began=resolve;});const blocked=new Promise(resolve=>{release=resolve;});
  const service=worker(async()=>{began();await blocked;});const stop=service.start();
  let timer;
  try {
    await service.drain(); // Finish the startup scan before the new report exists.
    const id=await completed();
    expect((await jobs.getJob(id)).status).toBe('completed');
    const notified=await Promise.race([started.then(()=>true),new Promise(resolve=>{timer=setTimeout(()=>resolve(false),1500);})]);
    expect(notified).toBe(true);
    release();await service.drain();
    expect((await get('SELECT status FROM report_email_outbox WHERE job_id=?',[id])).status).toBe('sent');
  } finally {clearTimeout(timer);release();stop();}
});
it('unsubscribes the completion wake-up when the mail worker stops',async()=>{
  const sent=[];const service=worker(async mail=>sent.push(mail));const stop=service.start();await service.drain();stop();
  const id=await completed();await new Promise(resolve=>setTimeout(resolve,40));
  expect(sent).toHaveLength(0);expect((await get('SELECT status FROM report_email_outbox WHERE job_id=?',[id])).status).toBe('pending');
});
