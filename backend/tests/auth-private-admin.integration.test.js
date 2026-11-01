import { once } from 'node:events';
import { createRequire } from 'node:module';
import request from 'supertest';
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const require = createRequire(import.meta.url);
const app = require('../src/app');
const { createTestDatabaseHarness, get, run } = require('../src/database');
const { createUserSession } = require('../src/auth/sessionService');
const users = require('../src/auth/sessionRepository');
const password = 'ArcDemo123!';
const envNames = ['ARC_AUTH_MODE', 'ARC_ADMIN_PORT', 'JACCOUNT_CLIENT_ID', 'JACCOUNT_CLIENT_SECRET', 'JACCOUNT_REDIRECT_URI'];
let harness, privateServer, priorEnv, privatePort;

function cookie(response, name = 'arc_session') {
  return response.headers['set-cookie']?.find(value => value.startsWith(name + '='))?.split(';')[0];
}
function campusProvider(profile) {
  vi.stubGlobal('fetch', vi.fn(async url => {
    if (url === 'https://jaccount.sjtu.edu.cn/oauth2/token') return { ok: true, json: async () => ({ access_token: 'private-test-token' }) };
    if (url === 'https://api.sjtu.edu.cn/v1/me/profile') return { ok: true, json: async () => ({ errno: 0, entities: [profile] }) };
    throw new Error('Unexpected provider URL');
  }));
}
async function campusLogin() {
  const start = await request(app).get('/api/auth/jaccount').expect(302);
  return request(app).get('/api/auth/jaccount/callback')
    .set('Cookie', cookie(start, 'arc_jaccount_state'))
    .query({ code: 'test-code', state: new URL(start.headers.location).searchParams.get('state') });
}

describe('production campus-only login and private administration', () => {
  beforeAll(async () => {
    priorEnv = Object.fromEntries(envNames.map(name => [name, process.env[name]]));
    harness = createTestDatabaseHarness({ label: 'private-admin-auth', seedDefault: true });
    await harness.setup();
    privateServer = app.listen(0, '127.0.0.1');
    await once(privateServer, 'listening');
    privatePort = privateServer.address().port;
    Object.assign(process.env, {
      ARC_ADMIN_PORT: String(privatePort), JACCOUNT_CLIENT_ID: 'private-admin-test',
      JACCOUNT_CLIENT_SECRET: 'private-admin-secret',
      JACCOUNT_REDIRECT_URI: 'http://localhost:3000/api/auth/jaccount/callback',
    });
  });
  beforeEach(() => { process.env.ARC_AUTH_MODE = 'jaccount-only'; });
  afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); });
  afterAll(async () => {
    await new Promise(resolve => privateServer.close(resolve));
    await harness.cleanup();
    for (const [name, value] of Object.entries(priorEnv)) {
      if (value === undefined) delete process.env[name]; else process.env[name] = value;
    }
  });

  it.each(['school_admin01', 'college_admin01', 'student01'])('rejects public password login for %s without issuing a session', async username => {
    const before = await get('SELECT count(*) AS count FROM auth_sessions');
    const response = await request(app).post('/api/auth/login').send({ username, password }).expect(403);
    expect(cookie(response)).toBeUndefined();
    expect(await get('SELECT count(*) AS count FROM auth_sessions')).toEqual(before);
  });
  it('cannot enable production public password login through a legacy configuration value', async () => {
    vi.stubEnv('NODE_ENV', 'production');
    process.env.ARC_AUTH_MODE = 'local';
    await request(app).post('/api/auth/login').send({ username: 'school_admin01', password }).expect(403);
  });
  it('does not trust forged host or forwarding headers as the private listener', async () => {
    const response = await request(app).post('/api/auth/login')
      .set('Host', `127.0.0.1:${privatePort}`).set('X-Forwarded-For', '127.0.0.1')
      .set('X-Forwarded-Host', 'localhost').set('X-Forwarded-Port', String(privatePort))
      .set('Forwarded', 'for=127.0.0.1;host=localhost')
      .send({ username: 'school_admin01', password }).expect(403);
    expect(cookie(response)).toBeUndefined();
  });
  it.each(['school_admin01', 'college_admin01'])('allows %s to authenticate only on the private listener', async username => {
    const response = await request(privateServer).post('/api/auth/login').send({ username, password }).expect(200);
    const session = cookie(response);
    expect(session).toBeTruthy();
    await request(privateServer).get('/api/auth/me').set('Cookie', session).expect(200);
    await request(app).get('/api/auth/me').set('Cookie', session).expect(401);
    await request(app).get('/api/normative/rules').set('Cookie', session).expect(401);
    await request(privateServer).post('/api/auth/logout').set('Cookie', session).expect(204);
  });
  it('rejects ordinary local accounts and bad administrator credentials on the private listener', async () => {
    const before = await get('SELECT count(*) AS count FROM auth_sessions');
    await request(privateServer).post('/api/auth/login').send({ username: 'student01', password, role: 'SCHOOL_ADMIN' }).expect(401);
    await request(privateServer).post('/api/auth/login').send({ username: 'school_admin01', password: 'wrong' }).expect(401);
    expect(await get('SELECT count(*) AS count FROM auth_sessions')).toEqual(before);
  });
  it('rejects untrusted browser origins and hosts on the private listener', async () => {
    await request(privateServer).post('/api/auth/login').set('Origin', 'https://untrusted.example')
      .send({ username: 'school_admin01', password }).expect(403);
    await request(privateServer).post('/api/auth/login').set('Host', 'untrusted.example')
      .send({ username: 'school_admin01', password }).expect(403);
  });
  it('does not restore old local-user sessions on the public site', async () => {
    const session = await createUserSession(await users.findUserByUsername('student01'));
    await request(app).get('/api/auth/me').set('Cookie', 'arc_session=' + session.sessionId).expect(401);
  });
  it('keeps campus users separate from same-named admins and denies admin endpoints', async () => {
    campusProvider({ id: 'public-campus-student', account: 'school_admin01', name: 'Campus Student', role: 'SCHOOL_ADMIN', userType: 'admin' });
    const response = await campusLogin();
    expect(response.headers.location).toBe('/paper-upload');
    const session = cookie(response);
    const me = await request(app).get('/api/auth/me').set('Cookie', session).expect(200);
    expect(me.body.user).toMatchObject({ id: 'jaccount:public-campus-student', role: 'STUDENT' });
    await request(app).get('/api/normative/duplication-corpus').set('Cookie', session).expect(403);
    await request(app).get('/api/normative/paper-lint/reports').set('Cookie', session).expect(200);
  });
  it('does not issue campus sessions for an administrator role already stored in the database', async () => {
    campusProvider({ id: 'campus-admin-role', account: 'campus-admin-role' });
    await campusLogin();
    await run("UPDATE auth_users SET role='SCHOOL_ADMIN' WHERE id='jaccount:campus-admin-role'");
    const before = await get('SELECT count(*) AS count FROM auth_sessions');
    const response = await campusLogin();
    expect(response.headers.location).toBe('/auth?jaccount_error=forbidden_role');
    expect(cookie(response)).toBeUndefined();
    expect(await get('SELECT count(*) AS count FROM auth_sessions')).toEqual(before);
    expect((await get("SELECT role FROM auth_users WHERE id='jaccount:campus-admin-role'")).role).toBe('SCHOOL_ADMIN');
  });
});
