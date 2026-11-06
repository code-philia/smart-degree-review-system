import express from 'express';
import request from 'supertest';
import { afterAll, beforeAll, expect, it } from 'vitest';
import { createRequire } from 'node:module';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
const require = createRequire(import.meta.url);
const { createTestDatabaseHarness, get, all, run } = require('../src/database');
const authRoutes = require('../src/auth/authRoutes');
const jobs = require('../src/normative/paperLintJobRepository');
const reports = require('../src/normative/paperLintReportRepository');
let harness, directory;
const cookies = {};
const app = express(); app.use('/api/auth', express.json(), authRoutes);
const pdf = Buffer.from('%PDF-1.7\nemail fixture');
const result = { type: 'paper_lint', rule_runs: [], summary: { finding_count: 0 } };

beforeAll(async () => {
  directory = fs.mkdtempSync(path.join(os.tmpdir(), 'report-email-'));
  process.env.PAPER_LINT_JOBS_DIR = path.join(directory, 'jobs');
  process.env.PAPER_LINT_REPORTS_DIR = path.join(directory, 'reports');
  harness = createTestDatabaseHarness({ label: 'report-email', seedDefault: true }); await harness.setup();
  await run("INSERT INTO auth_users(id,username,password_hash,role,scope) SELECT 'mail-user','mail-user',password_hash,'STUDENT','COLLEGE' FROM auth_users WHERE id='student01'");
  for (const username of ['mail-user', 'student01', 'supervisor01', 'school_admin01', 'college_admin01']) {
    const login = await request(app).post('/api/auth/login').send({ username, password: 'ArcDemo123!' }).expect(200);
    cookies[username] = login.headers['set-cookie'].find(v => v.startsWith('arc_session='));
  }
});
afterAll(async () => {
  await harness.cleanup(); fs.rmSync(directory, { recursive: true, force: true });
  delete process.env.PAPER_LINT_JOBS_DIR; delete process.env.PAPER_LINT_REPORTS_DIR;
});

it('exposes only the signed-in user notification destination and mail readiness', async () => {
  await request(app).get('/api/auth/notification-settings').expect(401);
  const settings = await request(app).get('/api/auth/notification-settings').set('Cookie', cookies['mail-user']).expect(200);
  expect(settings.body).toMatchObject({ email: null, fixed: false, delivery_available: false });
});
it.each(['student01','supervisor01','school_admin01','college_admin01'])('routes %s to the mandated administrator mailbox', async username => {
  const settings = await request(app).get('/api/auth/notification-settings').set('Cookie', cookies[username]).expect(200);
  expect(settings.body).toMatchObject({ email: '123090058@link.cuhk.edu.cn', fixed: true });
  await request(app).put('/api/auth/notification-settings').set('Cookie', cookies[username]).send({ email: 'other@example.com' }).expect(403);
});
it('lets a local user save one valid mailbox without changing any other account', async () => {
  await request(app).put('/api/auth/notification-settings').set('Cookie', cookies['mail-user']).send({ email: 'student@example.com', user_id: 'school_admin01' }).expect(200);
  const settings = await request(app).get('/api/auth/notification-settings').set('Cookie', cookies['mail-user']).expect(200);
  expect(settings.body.email).toBe('student@example.com');
  await request(app).put('/api/auth/notification-settings').set('Cookie', cookies['mail-user']).send({ email: 'a@example.com\r\nBcc:other@example.com' }).expect(400);
  await request(app).put('/api/auth/notification-settings').set('Cookie', cookies['mail-user']).send({ email: 'a@example.com,b@example.com' }).expect(400);
});
it('records exactly one notification atomically with a completed job', async () => {
  const id = await jobs.createJob({ userId:'mail-user', sourceFilename:'论文.pdf', pdfBuffer:pdf, selectedRuleIds:[] });
  await jobs.claimJob(id);
  await reports.createPaperLintReport({ userId:'mail-user', sourceFilename:'论文.pdf', pdfBuffer:pdf, selectedRuleIds:[], result, reportId:id });
  expect(await jobs.completeJob(id,id)).toBe(true);
  expect(await get("SELECT name FROM sqlite_master WHERE type='table' AND name='report_email_outbox'")).toBeTruthy();
  const rows = await all('SELECT * FROM report_email_outbox WHERE job_id=?',[id]);
  expect(rows).toHaveLength(1); expect(rows[0]).toMatchObject({ user_id:'mail-user', report_id:id, status:'pending', attempts:0 });
  expect(await jobs.completeJob(id,id)).toBe(false);
  expect(await all('SELECT * FROM report_email_outbox WHERE job_id=?',[id])).toHaveLength(1);
});
it('never schedules completion mail for a cancelled or failed detection', async () => {
  for (const cancelled of [true,false]) {
    const id = await jobs.createJob({ userId:'mail-user', sourceFilename:'failed.pdf', pdfBuffer:pdf, selectedRuleIds:[] });
    await jobs.claimJob(id);
    if (cancelled) await jobs.cancelJobForUser(id,'mail-user'); else await jobs.failJob(id,'failed');
    expect(await jobs.completeJob(id,id)).toBe(false);
    expect(await get("SELECT name FROM sqlite_master WHERE name='report_email_outbox'")).toBeTruthy();
    expect(await all('SELECT * FROM report_email_outbox WHERE job_id=?',[id])).toHaveLength(0);
  }
});
it('keeps a campus recipient server-authoritative for an existing session',async()=>{
  const {createUserSession}=require('../src/auth/sessionService');
  const user={id:'jaccount:existing-session',username:'jaccount:existing.person',role:'STUDENT',scope:'COLLEGE'};
  await run("INSERT INTO auth_users(id,username,password_hash,role,scope) VALUES (?,?,'!campus','STUDENT','COLLEGE')",[user.id,user.username]);
  const session=await createUserSession(user);const cookie='arc_session='+session.sessionId;
  const response=await request(app).get('/api/auth/notification-settings').set('Cookie',cookie).expect(200);
  expect(response.body).toMatchObject({email:'existing.person@sjtu.edu.cn',fixed:true});
  await request(app).put('/api/auth/notification-settings').set('Cookie',cookie).send({email:'override@example.test'}).expect(403);
});
