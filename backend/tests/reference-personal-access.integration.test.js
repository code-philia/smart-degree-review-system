import express from 'express';
import request from 'supertest';
import { createRequire } from 'node:module';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { beforeAll, beforeEach, afterAll, afterEach, it, expect, vi } from 'vitest';
const require = createRequire(import.meta.url);
const { createTestDatabaseHarness, run, all } = require('../src/database');
const settings = require('../src/auth/referenceSettingsService');
const { createUserSession } = require('../src/auth/sessionService');
const repository = require('../src/normative/paperLintJobRepository');
const reports = require('../src/normative/paperLintReportRepository');
const { createPaperLintJobService } = require('../src/normative/paperLintJobService');
const { createReviewPilotPaperLintRouter } = require('../src/normative/reviewPilotPaperLintRoutes');
const { runPaperLint } = require('../src/normative/reviewPilotPaperLintService');
const { runReferenceVerification } = require('../src/normative/referenceVerificationService');
const { verifyReference } = require('../src/normative/referenceVerificationCore');
const { requirePersonalReferenceCredentials } = require('../src/auth/referencePersonalAccess');
const rule = 'reference_verification_check';
const endpoint = '/paper-lint';
const pdf = Buffer.from('%PDF-1.7\nsynthetic');
const blocked = { status: 400, code: 'reference_key_required' };
const envKeys = ['PAPER_LINT_JOBS_DIR','PAPER_LINT_REPORTS_DIR','PAPER_LINT_JOB_CONCURRENCY',
  'REFERENCE_SETTINGS_ENCRYPTION_KEY','OPENALEX_API_KEYS','OPENALEX_API_KEY','PAPER_COMPILER_EVIDENCE_CONFIG'];
const savedEnv = Object.fromEntries(envKeys.map(key => [key, process.env[key]]));
let harness, directory, cookies, engine, jobs, app;
const title = 'Reliable metadata verification for scholarly references';
const entry = { title, authors: ['Smith, J.'], year: 2023, type_code: 'J', extraction_confidence: 'high' };
function input(userId = 'personal:alice', selectedRuleIds = [rule]) {
  return { userId, sourceFilename: 'private.pdf', pdfBuffer: pdf, selectedRuleIds, externalProcessingConsent: false };
}
function submit(user = 'personal:alice', selected = rule) {
  return request(app).post(`${endpoint}/run`).set('Cookie', cookies[user])
    .set('Content-Type', 'application/pdf').set('x-paper-lint-rule-ids', selected).send(pdf);
}
beforeAll(async () => {
  directory = await fs.mkdtemp(path.join(os.tmpdir(), 'reference-personal-access-'));
  Object.assign(process.env, { PAPER_LINT_JOBS_DIR: path.join(directory, 'jobs'), PAPER_LINT_REPORTS_DIR: path.join(directory, 'reports'),
    PAPER_LINT_JOB_CONCURRENCY: '1', REFERENCE_SETTINGS_ENCRYPTION_KEY: Buffer.alloc(32, 31).toString('base64'),
    OPENALEX_API_KEYS: 'platform-only-must-not-be-used', PAPER_COMPILER_EVIDENCE_CONFIG: path.join(directory, 'missing') });
  harness = createTestDatabaseHarness({ label: 'reference-personal-access' }); await harness.setup();
  cookies = {};
  for (const [id, role] of [['personal:alice','STUDENT'],['personal:bob','STUDENT'],['personal:admin','SCHOOL_ADMIN']]) {
    await run('INSERT INTO auth_users(id,username,password_hash,role,scope) VALUES(?,?,?,?,?)', [id,id,'unused',role,'SCHOOL']);
    cookies[id] = `arc_session=${encodeURIComponent((await createUserSession({ id })).sessionId)}`;
  }
  for (const [id, role] of [['student01','STUDENT'],['supervisor01','SUPERVISOR'],['college_admin01','COLLEGE_ADMIN'],['school_admin01','SCHOOL_ADMIN']]) {
    await run('INSERT INTO auth_users(id,username,password_hash,role,scope) VALUES(?,?,?,?,?)', [id,id,'unused',role,'SCHOOL']);
    cookies[id] = `arc_session=${encodeURIComponent((await createUserSession({ id })).sessionId)}`;
  }
});
beforeEach(async () => {
  await run('DELETE FROM user_reference_settings');
  engine = { MAX_PDF_BYTES: 50 * 1024 * 1024, validatePdf: vi.fn(), normalizeSelectedRuleIds: vi.fn(async ids => ids),
    runPaperLint: vi.fn(async ({ selectedRuleIds }) => ({ selectedRuleIds, result: { type: 'paper_lint', paper_title: 'Test',
      rule_runs: selectedRuleIds.map(rule_id => ({ rule_id, execution_status: 'completed', outcome: 'passed', findings: [] })), summary: {} } })) };
  jobs = createPaperLintJobService(engine);
  app = express(); app.use(endpoint, createReviewPilotPaperLintRouter(engine, undefined, jobs));
});
afterEach(async () => { await jobs.waitForIdle(); });
afterAll(async () => {
  await harness.cleanup(); await fs.rm(directory, { recursive: true, force: true });
  for (const [key,value] of Object.entries(savedEnv)) {
    if (value === undefined) delete process.env[key]; else process.env[key] = value;
  }
});

it('rejects an authenticated run without a personal key before persisting or executing a job despite platform keys', async () => {
  const before = await all('SELECT id FROM paper_lint_jobs');
  const response = await submit().expect(400);
  expect(response.body.error_code).toBe('reference_key_required');
  expect(response.text).not.toContain('platform-only');
  expect(await all('SELECT id FROM paper_lint_jobs')).toEqual(before);
  expect(engine.runPaperLint).not.toHaveBeenCalled();
});

it.each(['api_key','serpapi_key'])('allows an owned saved %s and does not borrow it for another user', async field => {
  await settings.saveReferenceSettings('personal:alice', { [field]: 'owned-personal-key' });
  await submit().expect(202); await jobs.waitForIdle();
  expect(engine.runPaperLint).toHaveBeenCalledTimes(1);
  await submit('personal:bob').expect(400);
  expect(engine.runPaperLint).toHaveBeenCalledTimes(1);
});

it('rejects direct repository and trusted reservations without personal credentials', async () => {
  await expect(repository.createJob(input())).rejects.toMatchObject(blocked);
  await expect(repository.createJob({ ...input(), allowSharedQuota: true })).rejects.toMatchObject(blocked);
  await expect(repository.createJob({ ...input('personal:admin'), trustedBatchMaxPdfBytes: 64 * 1024 * 1024 })).rejects.toMatchObject(blocked);
});

it('blocks trusted start after its personal key is removed without marking it started', async () => {
  await settings.saveReferenceSettings('personal:admin', { serpapi_key: 'owned-personal-key' });
  const id = await repository.createJob({ ...input('personal:admin'), trustedBatchMaxPdfBytes: 64 * 1024 * 1024 });
  await settings.deleteReferenceSettings('personal:admin', 'serpapi');
  const response = await request(app).post(`${endpoint}/jobs/${id}/start`).set('Cookie', cookies['personal:admin']).send({}).expect(400);
  expect(response.body.error_code).toBe('reference_key_required');
  expect(JSON.parse((await repository.getJob(id)).reuse_json).operator_options.start_requested).toBe(false);
  expect(engine.runPaperLint).not.toHaveBeenCalled();
});

it('blocks incremental execution without credentials while keeping the owned stored report readable', async () => {
  const source = await reports.createPaperLintReport({ ...input(), selectedRuleIds: ['sjtu_rule_18'],
    result: { type: 'paper_lint', rule_runs: [{ rule_id: 'sjtu_rule_18', execution_status: 'completed', outcome: 'passed', findings: [] }], summary: {} } });
  const id = typeof source === 'string' ? source : source.id;
  await request(app).get(`${endpoint}/reports/${id}`).set('Cookie', cookies['personal:alice']).expect(200);
  const response = await request(app).post(`${endpoint}/reports/${id}/rerun`).set('Cookie', cookies['personal:alice'])
    .send({ selected_rule_ids: [rule] }).expect(400);
  expect(response.body.error_code).toBe('reference_key_required');
  expect(engine.runPaperLint).not.toHaveBeenCalled();
});

it('keeps a completed reference report readable and reusable while another rule runs without personal keys', async () => {
  const source = await reports.createPaperLintReport({ ...input(), result: { type: 'paper_lint',
    rule_runs: [{ rule_id: rule, execution_status: 'completed', outcome: 'passed', findings: [] }], summary: {} } });
  const history = await request(app).get(`${endpoint}/reports/${source.id}`).set('Cookie', cookies['personal:alice']).expect(200);
  expect(history.body.result.rule_runs[0].rule_id).toBe(rule);
  await request(app).post(`${endpoint}/reports/${source.id}/rerun`).set('Cookie', cookies['personal:alice'])
    .send({ selected_rule_ids: ['sjtu_rule_18'] }).expect(202);
  await jobs.waitForIdle();
  expect(engine.runPaperLint).toHaveBeenCalledTimes(1);
  expect(engine.runPaperLint.mock.calls[0][0].selectedRuleIds).toEqual(['sjtu_rule_18']);
});

it('rechecks queued credentials at execution and leaves unrelated rules usable without a key', async () => {
  let release, entered;
  const enteredPromise = new Promise(resolve => { entered = resolve; });
  const blocker = new Promise(resolve => { release = resolve; });
  engine.runPaperLint.mockImplementationOnce(async () => { entered(); await blocker; return { result: { type: 'paper_lint', rule_runs: [], summary: {} } }; });
  await jobs.enqueue(input('personal:bob', ['sjtu_rule_18'])); await enteredPromise;
  try {
    await settings.saveReferenceSettings('personal:alice', { api_key: 'owned-personal-key' });
    const queued = await jobs.enqueue(input());
    await settings.deleteReferenceSettings('personal:alice');
    release(); await jobs.waitForIdle();
    const failed = await jobs.getForUser(queued.job_id, 'personal:alice');
    expect(failed.status).toBe('failed');
    expect(failed.error_message).toContain('OpenAlex');
    expect(engine.runPaperLint).toHaveBeenCalledTimes(1);
    await submit('personal:alice', 'sjtu_rule_18').expect(202); await jobs.waitForIdle();
    expect(engine.runPaperLint).toHaveBeenCalledTimes(2);
  } finally { release(); }
});

it('blocks direct rule and direct paper execution before extraction or network work without a personal key', async () => {
  const extractor = vi.fn(async () => ({ entries: [], coverage_complete: true }));
  await expect(runReferenceVerification('unused.pdf', { credentials: { platformKeys: ['platform-only'] }, extractor })).rejects.toMatchObject(blocked);
  expect(extractor).not.toHaveBeenCalled();
  await expect(runPaperLint({ ...input(), userId: 'personal:bob' })).rejects.toMatchObject(blocked);
  const fetchImpl = vi.fn();
  await expect(verifyReference(entry, { platformKeys: ['platform-only'], fetchImpl })).rejects.toMatchObject(blocked);
  expect(fetchImpl).not.toHaveBeenCalled();
});

it.each(['personalKey','serpapiKey'])('uses only the supplied personal %s and can verify an actual catalog record', async field => {
  await settings.saveReferenceSettings('personal:alice', { [field === 'personalKey' ? 'api_key' : 'serpapi_key']: 'owned-personal-key' });
  const destinations = [];
  const fetchImpl = async inputUrl => {
    const url = new URL(inputUrl); destinations.push(url);
    if (url.hostname === 'api.openalex.org') {
      expect(field).toBe('personalKey'); expect(url.searchParams.get('api_key')).toBe('owned-personal-key');
      return Response.json({ results: [{ id: 'https://openalex.org/W123', title, publication_year: 2023,
        authorships: [{ author: { display_name: 'John Smith' } }] }] });
    }
    if (url.hostname === 'serpapi.com') {
      expect(field).toBe('serpapiKey'); expect(url.searchParams.get('api_key')).toBe('owned-personal-key');
      return Response.json({ organic_results: [{ title, link: 'https://example.test/publication',
        publication_info: { authors: [{ name: 'John Smith' }], summary: 'John Smith - Journal, 2023' } }] });
    }
    expect(url.hostname).toBe('api.crossref.org'); return Response.json({ message: { items: [] } });
  };
  const result = await runReferenceVerification('unused.pdf', { userId: 'personal:alice',
    extractor: async () => ({ entries: [entry], coverage_complete: true }),
    verify: (row, options) => verifyReference(row, { ...options, fetchImpl }),
  });
  expect(result.rule_runs[0].params.reference_verification.entries[0].category).toBe('verified');
  expect(destinations.some(url => url.hostname === (field === 'personalKey' ? 'api.openalex.org' : 'serpapi.com'))).toBe(true);
  if (field === 'serpapiKey') expect(destinations.some(url => url.hostname === 'api.openalex.org')).toBe(false);
  expect(destinations.some(url => url.searchParams.get('api_key') === 'platform-only')).toBe(false);
  expect(JSON.stringify(result)).not.toContain('owned-personal-key');
});

it.each(['student01','supervisor01','college_admin01','school_admin01'])('permits shared quota only for the persisted authorized local account %s', async userId => {
  const credentials = await requirePersonalReferenceCredentials(userId);
  expect(credentials).toMatchObject({ allowSharedQuota: true, personalKey: null, serpapiKey: null, platformKeys: ['platform-only-must-not-be-used'] });
  expect((await settings.getReferenceSettings(userId)).can_verify_references).toBe(true);
  await submit(userId).expect(202); await jobs.waitForIdle();
  expect(engine.runPaperLint).toHaveBeenCalledTimes(1);
});

it('denies shared credentials for a privileged nonlocal user, a jAccount username collision and a local account with the wrong persisted role', async () => {
  await expect(requirePersonalReferenceCredentials('personal:admin')).rejects.toMatchObject(blocked);
  expect((await settings.getReferenceSettings('personal:admin')).can_verify_references).toBe(false);
  await run("UPDATE auth_users SET role='SCHOOL_ADMIN' WHERE id='student01'");
  await expect(requirePersonalReferenceCredentials('student01')).rejects.toMatchObject(blocked);
  await run("UPDATE auth_users SET username='reserved-student01' WHERE id='student01'");
  await run("INSERT INTO auth_users(id,username,password_hash,role,scope) VALUES('jaccount:student01','student01','unused','STUDENT','SCHOOL')");
  try {
    await expect(requirePersonalReferenceCredentials('jaccount:student01')).rejects.toMatchObject(blocked);
    await expect(requirePersonalReferenceCredentials('student01')).rejects.toMatchObject(blocked);
    expect((await settings.getReferenceSettings('jaccount:student01')).can_verify_references).toBe(false);
  } finally {
    await run("DELETE FROM auth_users WHERE id='jaccount:student01'");
    await run("UPDATE auth_users SET username='student01',role='STUDENT' WHERE id='student01'");
  }
});

it.each([true,false])('lets an authorized local account use shared OpenAlex with a platform key=%s', async usePlatform => {
  const previous = process.env.OPENALEX_API_KEYS;
  process.env.OPENALEX_API_KEYS = usePlatform ? 'local-shared-openalex' : '';
  try {
    const credentials = await requirePersonalReferenceCredentials('student01');
    const destinations = [];
    const result = await verifyReference(entry, { ...credentials, fetchImpl: async inputUrl => {
      const url = new URL(inputUrl); destinations.push(url);
      return url.hostname === 'api.openalex.org' ? Response.json({ results: [{ id:'https://openalex.org/W123', title,
        publication_year:2023, authorships:[{author:{display_name:'John Smith'}}] }] }) : Response.json({message:{items:[]}});
    } });
    expect(result.category).toBe('verified');
    expect(destinations.filter(url => url.hostname === 'api.openalex.org').map(url => url.searchParams.get('api_key')))
      .toEqual([usePlatform ? 'local-shared-openalex' : null]);
  } finally { process.env.OPENALEX_API_KEYS = previous; }
});
