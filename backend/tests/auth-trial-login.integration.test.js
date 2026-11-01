import { createRequire } from 'node:module';
import request from 'supertest';
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const require = createRequire(import.meta.url);
const app = require('../src/app');
const { createTestDatabaseHarness, get, run } = require('../src/database');
const { createUserSession } = require('../src/auth/sessionService');
const users = require('../src/auth/sessionRepository');
const password = 'ArcDemo123!';
const origin = 'http://localhost:3000';
let harness;
const saved = {};
function trial(payload, customOrigin = origin) {
  return request(app).post('/api/auth/trial-login').set('Host','localhost:3000')
    .set('Origin',customOrigin).send(payload);
}
function cookie(response) { return response.headers['set-cookie']?.find(v=>v.startsWith('arc_session='))?.split(';')[0]; }

describe('hidden trial sign-in', () => {
  beforeAll(async () => {
    for (const key of ['ARC_AUTH_MODE','ARC_TRIAL_LOGIN_ENABLED','ARC_TRIAL_LOGIN_ORIGIN']) saved[key]=process.env[key];
    harness=createTestDatabaseHarness({label:'hidden-trial-login',seedDefault:true});
    await harness.setup();
  });
  beforeEach(() => {
    Object.assign(process.env,{ARC_AUTH_MODE:'jaccount-only',ARC_TRIAL_LOGIN_ENABLED:'1',ARC_TRIAL_LOGIN_ORIGIN:origin});
    try { require('../src/auth/trialLoginPolicy').trialAttempts.clear(); } catch { /* RED: policy not implemented yet. */ }
  });
  afterAll(async () => {
    await harness.cleanup();
    for (const [key,value] of Object.entries(saved)) {
      if(value===undefined) delete process.env[key]; else process.env[key]=value;
    }
    vi.restoreAllMocks();
  });
  it.each([
    ['student01','STUDENT'],['supervisor01','SUPERVISOR'],
    ['college_admin01','COLLEGE_ADMIN'],['school_admin01','SCHOOL_ADMIN'],
  ])('authenticates %s with its existing role and restores and revokes its session',async (username,role) => {
    const response=await trial({username,password,role:'SCHOOL_ADMIN'}).expect(200);
    expect(response.body.user).toMatchObject({id:username,username,role});
    const session=cookie(response);
    expect(session).toBeTruthy();
    expect(response.headers['set-cookie'][0]).toContain('HttpOnly');
    expect(response.headers['set-cookie'][0]).toContain('SameSite=Lax');
    expect((await request(app).get('/api/auth/me').set('Cookie',session).expect(200)).body.user.role).toBe(role);
    await request(app).get('/api/normative/duplication-corpus').set('Cookie',session)
      .expect(role==='SCHOOL_ADMIN'?200:403);
    await request(app).post('/api/auth/logout').set('Cookie',session).expect(204);
    await request(app).get('/api/auth/me').set('Cookie',session).expect(401);
  });
  it('keeps the normal public password endpoint closed',async () => {
    await request(app).post('/api/auth/login').send({username:'school_admin01',password}).expect(403);
  });
  it('fails closed when trial sign-in is disabled or its origin is not configured',async () => {
    delete process.env.ARC_TRIAL_LOGIN_ENABLED;
    expect(cookie(await trial({username:'school_admin01',password}).expect(403))).toBeUndefined();
    process.env.ARC_TRIAL_LOGIN_ENABLED='1';delete process.env.ARC_TRIAL_LOGIN_ORIGIN;
    await trial({username:'school_admin01',password}).expect(403);
  });
  it('rejects cross-origin, missing-origin, forged-host and form requests without issuing sessions',async () => {
    const before=await get('SELECT count(*) AS n FROM auth_sessions');
    await trial({username:'school_admin01',password},'https://untrusted.example').expect(403);
    await request(app).post('/api/auth/trial-login').set('Host','localhost:3000').send({username:'school_admin01',password}).expect(403);
    await trial({username:'school_admin01',password}).set('Host','untrusted.example').expect(403);
    await trial({username:'school_admin01',password}).set('Sec-Fetch-Site','cross-site').expect(403);
    await request(app).post('/api/auth/trial-login').set('Host','localhost:3000').set('Origin',origin)
      .type('form').send({username:'school_admin01',password}).expect(403);
    expect(await get('SELECT count(*) AS n FROM auth_sessions')).toEqual(before);
  });
  it('rejects wrong passwords and other accounts with the same generic error',async () => {
    const wrong=await trial({username:'student01',password:'wrong'}).expect(401);
    const other=await trial({username:'unlisted-account',password}).expect(401);
    expect(wrong.body).toEqual(other.body);
    expect(cookie(wrong)).toBeUndefined();expect(cookie(other)).toBeUndefined();
  });
  it('rejects a campus identity or altered role even if its username matches a trial account',async () => {
    const existing=await users.findUserByUsername('supervisor01');
    try {
      await run("UPDATE auth_users SET role='SCHOOL_ADMIN' WHERE id='supervisor01'");
      await trial({username:'supervisor01',password}).expect(401);
    } finally { await run('UPDATE auth_users SET role=? WHERE id=?',[existing.role,existing.id]); }
  });
  it('does not accept old private administrator cookies or prefixed forgeries on the public listener',async () => {
    const session=await createUserSession(await users.findUserByUsername('school_admin01'));
    await request(app).get('/api/auth/me').set('Cookie','arc_session='+session.sessionId).expect(401);
    await request(app).get('/api/auth/me').set('Cookie','arc_session=trial:'+session.sessionId).expect(401);
  });
  it('revokes public trial access when the feature is disabled',async () => {
    const response=await trial({username:'school_admin01',password}).expect(200);
    process.env.ARC_TRIAL_LOGIN_ENABLED='0';
    await request(app).get('/api/auth/me').set('Cookie',cookie(response)).expect(401);
  });
  it('rechecks the role after a trial session has been created',async () => {
    const response=await trial({username:'student01',password}).expect(200);
    try {
      await run("UPDATE auth_users SET role='SCHOOL_ADMIN' WHERE id='student01'");
      await request(app).get('/api/auth/me').set('Cookie',cookie(response)).expect(401);
      await request(app).get('/api/normative/duplication-corpus').set('Cookie',cookie(response)).expect(401);
    } finally { await run("UPDATE auth_users SET role='STUDENT' WHERE id='student01'"); }
  });
  it('limits repeated failures and ignores spoofed forwarding addresses',async () => {
    for(let i=0;i<5;i++) await trial({username:'school_admin01',password:'wrong'})
      .set('X-Forwarded-For','192.0.2.'+i).expect(401);
    const before=await get('SELECT count(*) AS n FROM auth_sessions');
    const limited=await trial({username:'school_admin01',password}).set('X-Forwarded-For','192.0.2.200').expect(429);
    expect(Number(limited.headers['retry-after'])).toBeGreaterThan(0);
    expect(await get('SELECT count(*) AS n FROM auth_sessions')).toEqual(before);
  });
});
