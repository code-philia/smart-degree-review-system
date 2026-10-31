import crypto from 'node:crypto';
import { createRequire } from 'node:module';
import request from 'supertest';
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const require = createRequire(import.meta.url);
const app = require('../src/app');
const { createTestDatabaseHarness, get, run } = require('../src/database');
const tokenUrl = 'https://jaccount.sjtu.edu.cn/oauth2/token';
const profileUrl = 'https://api.sjtu.edu.cn/v1/me/profile';
const callback = 'http://localhost:3000/api/auth/jaccount/callback';
const envNames = ['JACCOUNT_CLIENT_ID', 'JACCOUNT_CLIENT_SECRET', 'JACCOUNT_REDIRECT_URI'];
let harness;
let oldEnv;

function cookie(response, name) {
  return response.headers['set-cookie']?.find((value) => value.startsWith(name + '='))?.split(';')[0];
}

async function start() {
  const response = await request(app).get('/api/auth/jaccount').set('Host', 'untrusted.example').expect(302);
  return { response, state: new URL(response.headers.location).searchParams.get('state'), browserCookie: cookie(response, 'arc_jaccount_state') };
}

function provider(profile, { tokenStatus = 200, errno = 0 } = {}) {
  const fetch = vi.fn(async (url, options) => {
    if (url === tokenUrl) {
      const form = new URLSearchParams(options.body);
      expect(options.method).toBe('POST');
      expect(form.get('grant_type')).toBe('authorization_code');
      expect(form.get('redirect_uri')).toBe(callback);
      expect(form.get('client_id')).toBe('test-campus-client');
      expect(form.get('client_secret')).toBe('test-campus-secret');
      expect(form.get('code')).toBe('approved-code');
      return { ok: tokenStatus === 200, json: async () => tokenStatus === 200 ? { access_token: 'private-campus-token', token_type: 'Bearer', expires_in: 1800 } : { error: 'invalid_grant', error_description: 'test-campus-secret' } };
    }
    if (url === profileUrl) {
      expect(options.headers.Authorization).toBe('Bearer private-campus-token');
      return { ok: true, json: async () => ({ errno, error: errno ? 'denied' : 'success', total: 0, entities: profile ? [profile] : [] }) };
    }
    throw new Error('Unexpected provider request');
  });
  vi.stubGlobal('fetch', fetch);
  return fetch;
}

function finish(login, extra = {}) {
  return request(app).get('/api/auth/jaccount/callback').set('Cookie', login.browserCookie)
    .query({ code: 'approved-code', state: login.state, ...extra });
}

describe('campus authorization-code sign-in', () => {
  beforeAll(async () => {
    harness = createTestDatabaseHarness({ label: 'jaccount', seedDefault: true });
    await harness.setup();
  });
  beforeEach(() => {
    oldEnv = Object.fromEntries(envNames.map((name) => [name, process.env[name]]));
    Object.assign(process.env, { JACCOUNT_CLIENT_ID: 'test-campus-client', JACCOUNT_CLIENT_SECRET: 'test-campus-secret', JACCOUNT_REDIRECT_URI: callback });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    for (const [name, value] of Object.entries(oldEnv)) {
      if (value === undefined) delete process.env[name]; else process.env[name] = value;
    }
  });
  afterAll(async () => harness.cleanup());

  it('starts essential authorization with a fixed callback and a private browser-bound state', async () => {
    const login = await start();
    const url = new URL(login.response.headers.location);
    expect(url.origin + url.pathname).toBe('https://jaccount.sjtu.edu.cn/oauth2/authorize');
    expect(url.searchParams.get('scope')).toBe('essential');
    expect(url.searchParams.get('response_type')).toBe('code');
    expect(url.searchParams.get('redirect_uri')).toBe(callback);
    expect(login.state.length).toBeGreaterThanOrEqual(32);
    expect(login.browserCookie).toBe('arc_jaccount_state=' + login.state);
    expect(login.response.headers['set-cookie'].join(';')).toMatch(/HttpOnly/);
    expect(login.response.headers['set-cookie'].join(';')).toMatch(/SameSite=Lax/);
    expect(login.response.headers.location).not.toContain('test-campus-secret');
  });

  it('exchanges the code server-side and creates a restorable application session', async () => {
    provider({ id: 'person-success', account: 'campus-user', name: 'Campus User', userType: 'student' });
    const response = await finish(await start()).expect(302);
    expect(response.headers.location).toBe('/paper-upload');
    const sessionCookie = cookie(response, 'arc_session');
    expect(sessionCookie).toBeTruthy();
    const me = await request(app).get('/api/auth/me').set('Cookie', sessionCookie).expect(200);
    expect(me.body.user).toMatchObject({ id: 'jaccount:person-success', username: 'jaccount:campus-user', displayName: 'Campus User', role: 'STUDENT', scope: 'COLLEGE' });
    expect(JSON.stringify(response.headers)).not.toContain('private-campus-token');
    expect(JSON.stringify(me.body)).not.toContain('test-campus-secret');
    await request(app).post('/api/auth/logout').set('Cookie', sessionCookie).expect(204);
    await request(app).get('/api/auth/me').set('Cookie', sessionCookie).expect(401);
  });

  it('rejects missing or mismatched browser state before contacting campus APIs', async () => {
    const fetch = provider({ id: 'never-created', account: 'never-created' });
    const login = await start();
    await request(app).get('/api/auth/jaccount/callback').query({ code: 'approved-code', state: login.state }).expect(302)
      .expect('Location', '/auth?jaccount_error=state');
    await finish(login, { state: 'wrong-state' }).expect(302).expect('Location', '/auth?jaccount_error=state');
    expect(fetch).not.toHaveBeenCalled();
    expect(await get("SELECT id FROM auth_users WHERE id='jaccount:never-created'")).toBeNull();
  });

  it('consumes state once so a captured callback cannot create another session', async () => {
    const fetch = provider({ id: 'person-replay', account: 'replay' });
    const login = await start();
    await finish(login).expect(302).expect('Location', '/paper-upload');
    await finish(login).expect(302).expect('Location', '/auth?jaccount_error=state');
    expect(fetch).toHaveBeenCalledTimes(2);
    expect((await get("SELECT COUNT(*) AS count FROM auth_sessions WHERE user_id='jaccount:person-replay'")).count).toBe(1);
  });

  it('rejects expired state without exchanging an authorization code', async () => {
    const fetch = provider({ id: 'person-expired', account: 'expired' });
    const login = await start();
    await run('UPDATE auth_jaccount_states SET expires_at=? WHERE state_hash=?', ['2000-01-01T00:00:00.000Z', crypto.createHash('sha256').update(login.state).digest('hex')]);
    await finish(login).expect(302).expect('Location', '/auth?jaccount_error=state');
    expect(fetch).not.toHaveBeenCalled();
  });

  it('handles a declined campus login without creating a fake session', async () => {
    const fetch = provider({ id: 'person-declined', account: 'declined' });
    const response = await finish(await start(), { error: 'access_denied', code: '' }).expect(302);
    expect(response.headers.location).toBe('/auth?jaccount_error=denied');
    expect(cookie(response, 'arc_session')).toBeUndefined();
    expect(fetch).not.toHaveBeenCalled();
  });

  it('does not merge a campus account into a same-named local administrator', async () => {
    provider({ id: 'person-collision', account: 'school_admin01', name: 'Campus Staff', userType: 'faculty' });
    const response = await finish(await start()).expect(302).expect('Location', '/paper-upload');
    const me = await request(app).get('/api/auth/me').set('Cookie', cookie(response, 'arc_session')).expect(200);
    expect(me.body.user.role).toBe('STUDENT');
    expect(me.body.user.id).toBe('jaccount:person-collision');
    expect((await get("SELECT role FROM auth_users WHERE id='school_admin01'")).role).toBe('SCHOOL_ADMIN');
    await request(app).post('/api/auth/login').send({ username: 'jaccount:school_admin01', password: 'anything' }).expect(401);
  });

  it('keeps one campus identity and preserves roles assigned by the application', async () => {
    provider({ id: 'person-repeat', account: 'repeat', name: '原姓名', userType: 'student' });
    await finish(await start()).expect(302).expect('Location', '/paper-upload');
    await run("UPDATE auth_users SET role='SUPERVISOR' WHERE id='jaccount:person-repeat'");
    provider({ id: 'person-repeat', account: 'repeat', name: ' 更新姓名 ', userType: 'student' });
    const response = await finish(await start()).expect(302).expect('Location', '/paper-upload');
    const me = await request(app).get('/api/auth/me').set('Cookie', cookie(response, 'arc_session')).expect(200);
    expect(me.body.user.role).toBe('SUPERVISOR');
    expect(me.body.user.displayName).toBe('更新姓名');
    expect((await get("SELECT display_name FROM auth_users WHERE id='jaccount:person-repeat'")).display_name).toBe('更新姓名');
    expect((await get("SELECT COUNT(*) AS count FROM auth_users WHERE id='jaccount:person-repeat'")).count).toBe(1);
  });

  it.each([undefined, '', '  ', { unexpected: 'value' }])('preserves a stored name when a later profile has no usable name (%j)', async (name) => {
    const id = 'person-name-fallback-' + String(name);
    provider({ id, account: id, name: '张三' });
    await finish(await start()).expect(302);
    provider({ id, account: id, name });
    const response = await finish(await start()).expect(302);
    const me = await request(app).get('/api/auth/me').set('Cookie', cookie(response, 'arc_session')).expect(200);
    expect(me.body.user.displayName).toBe('张三');
  });

  it.each([{ profile: null, errno: 0 }, { profile: { account: 'no-person-id' }, errno: 0 }, { profile: { id: 'untrusted', account: 'untrusted' }, errno: 10002 }])('rejects missing or unauthenticated profile data ($errno)', async ({ profile, errno }) => {
    provider(profile, { errno });
    const response = await finish(await start()).expect(302);
    expect(response.headers.location).toBe('/auth?jaccount_error=provider');
    expect(cookie(response, 'arc_session')).toBeUndefined();
    expect(await get("SELECT id FROM auth_users WHERE id='jaccount:untrusted'")).toBeNull();
  });

  it('hides upstream error details and creates no session on a token error', async () => {
    provider(null, { tokenStatus: 400 });
    const response = await finish(await start()).expect(302).expect('Location', '/auth?jaccount_error=provider');
    expect(cookie(response, 'arc_session')).toBeUndefined();
    expect(JSON.stringify(response)).not.toContain('test-campus-secret');
  });

  it('handles a network failure without exposing provider internals', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('private-campus-token')));
    await finish(await start()).expect(302).expect('Location', '/auth?jaccount_error=provider');
  });

  it('reports an unconfigured campus login without exposing any configuration values', async () => {
    delete process.env.JACCOUNT_CLIENT_SECRET;
    const response = await request(app).get('/api/auth/jaccount/config').expect(200);
    expect(response.body).toEqual({ enabled: false });
    await request(app).get('/api/auth/jaccount').expect(302).expect('Location', '/auth?jaccount_error=unavailable');
  });
});
