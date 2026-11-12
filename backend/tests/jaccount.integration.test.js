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

  it('stores the authenticated campus mailbox for completion notifications', async () => {
    provider({ id: 'mail-profile', account: 'mail.profile', email: 'actual@sjtu.edu.cn' });
    const response = await finish(await start()).expect(302);
    const me = await request(app).get('/api/auth/me').set('Cookie', cookie(response, 'arc_session')).expect(200);
    expect(me.body.user.email).toBe('actual@sjtu.edu.cn');
  });

  it('returns to the requested report after campus sign-in',async()=>{
    provider({id:'return-report',account:'return.report'});
    const response=await request(app).get('/api/auth/jaccount').query({return_to:'/reports/pdf/123e4567-e89b-12d3-a456-426614174000'}).expect(302);
    const login={state:new URL(response.headers.location).searchParams.get('state'),browserCookie:cookie(response,'arc_jaccount_state')};
    await finish(login).expect(302).expect('Location','/reports/pdf/123e4567-e89b-12d3-a456-426614174000');
  });
  it.each(['zh','en'])('preserves the %s report link through the campus OAuth round trip',async lang=>{
    provider({id:'return-report-'+lang,account:'return.report.'+lang});
    const returnTo='/reports/pdf/123e4567-e89b-12d3-a456-426614174000?lang='+lang;
    const response=await request(app).get('/api/auth/jaccount').query({return_to:returnTo}).expect(302);
    const login={state:new URL(response.headers.location).searchParams.get('state'),browserCookie:cookie(response,'arc_jaccount_state')};
    await finish(login).expect(302).expect('Location',returnTo);
  });
  it.each(['https://evil.example','//evil.example','/\\evil.example','/reports/pdf/../../admin',
    '/reports/pdf/id?lang=en&next=https://evil.example','/reports/pdf/id?lang=fr',
    '/reports/pdf/id?lang=en&lang=zh','/reports/pdf/id?lang=en#//evil.example',
    '/reports/pdf/id?lang=%65n','/reports/pdf/id%2F..%2Fadmin?lang=en',
    '/reports/pdf/id?return_to=https://evil.example','/reports/pdf/id?lang=en%0d%0aLocation:https://evil.example',
    '/reports/pdf/id?lang=en%26next%3Dhttps://evil.example',
    '/reports/pdf/id?lang=en\n','/reports/pdf/id\r','/reports/pdf/id?lang=zh\u2028','/reports/pdf/id\u2029'])('does not use an unsafe return path %s',async returnTo=>{
    provider({id:'unsafe-'+returnTo,account:'unsafe'+Buffer.from(returnTo).toString('hex').slice(0,60)});
    const response=await request(app).get('/api/auth/jaccount').query({return_to:returnTo}).expect(302);
    const login={state:new URL(response.headers.location).searchParams.get('state'),browserCookie:cookie(response,'arc_jaccount_state')};
    await finish(login).expect(302).expect('Location','/paper-upload');
  });

  it('uses the institutional mailbox when essential profile omits email', async () => {
    provider({ id: 'mail-essential', account: 'mail.essential' });
    const response = await finish(await start()).expect(302);
    const me = await request(app).get('/api/auth/me').set('Cookie', cookie(response, 'arc_session')).expect(200);
    expect(me.body.user.email).toBe('mail.essential@sjtu.edu.cn');
  });
  it('reactivates a missing-recipient notification after a successful campus login',async()=>{
    provider({id:'mail-recovery',account:'mail.recovery'});await finish(await start()).expect(302);
    await run("INSERT INTO paper_lint_reports(id,user_id,source_filename,source_pdf_path,selected_rule_ids_json,result_json,created_at) VALUES ('mail-recovery-report','jaccount:mail-recovery','paper.pdf','unused','[]','{}','2026-11-07')");
    await run("INSERT INTO paper_lint_jobs(id,user_id,source_filename,source_pdf_path,selected_rule_ids_json,status,report_id,created_at,updated_at) VALUES ('mail-recovery-job','jaccount:mail-recovery','paper.pdf','unused','[]','completed','mail-recovery-report','2026-11-07','2026-11-07')");
    await run("INSERT INTO report_email_outbox(job_id,user_id,report_id,status,error_code,next_attempt_at,created_at,updated_at) VALUES ('mail-recovery-job','jaccount:mail-recovery','mail-recovery-report','blocked','missing_recipient','2026-11-07','2026-11-07','2026-11-07')");
    provider({id:'mail-recovery',account:'mail.recovery',email:'recovered@sjtu.edu.cn'});await finish(await start()).expect(302);
    expect((await get("SELECT status FROM report_email_outbox WHERE job_id='mail-recovery-job'")).status).toBe('pending');
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

  it.each([
    ['CN','zh'],['CHN','zh'],['156','zh'],[' cn ','zh'],
    ['US','en'],['USA','en'],['840','en'],['GBR','en'],['826','en'],['JP','en'],['JPN','en'],['392','en'],['DZ','en'],['DZA','en'],['012','en'],['12','en'],
    [undefined,null],['',null],['ZZ',null],['ZZZ',null],['001',null],['999',null],[156,null],[{},null],['China',null],
    ['HK',null],['HKG',null],['344',null],['MO',null],['MAC',null],['446',null],['TW',null],['TWN',null],['158',null],
  ])('defaults the authenticated session language only for recognized nationality code %j',async (gjm,expected) => {
    const id='nationality-'+crypto.randomUUID();
    provider({id,account:id,name:'Locale Test',identities:[{isDefault:true,userType:'student',gjm}]});
    const response=await finish(await start()).expect(302);
    const me=await request(app).get('/api/auth/me').set('Cookie',cookie(response,'arc_session')).expect(200);
    if(expected){
      expect(me.body.user.defaultLocale).toBe(expected);
      expect((await get('SELECT default_locale FROM auth_users WHERE id=?',['jaccount:'+id])).default_locale).toBe(expected);
    }else expect(me.body.user).not.toHaveProperty('defaultLocale');
    expect(me.body.user).not.toHaveProperty('gjm');
    expect(me.body.user).not.toHaveProperty('nationality');
  });
  it.each([
    [[{isDefault:true,gjm:'CN'},{gjm:'US'}],'zh'],
    [[{isDefault:true},{gjm:'US'}],null],
    [[{gjm:'CN'},{gjm:'US'}],null],
    [[{gjm:'US'},{gjm:'USA'}],'en'],
    [[{isDefault:true,gjm:'CN'},{isDefault:true,gjm:'US'}],null],
    [[],null],[{},null],[null,null],[[null,{}],null],
  ])('handles default and conflicting identity metadata without guessing: %j',async (identities,expected) => {
    const id='identities-'+crypto.randomUUID();provider({id,account:id,name:'English Name',gjm:'US',identities});
    const response=await finish(await start()).expect(302);
    const me=await request(app).get('/api/auth/me').set('Cookie',cookie(response,'arc_session')).expect(200);
    if(expected)expect(me.body.user.defaultLocale).toBe(expected);
    else expect(me.body.user).not.toHaveProperty('defaultLocale');
  });
  it('retains an established default if a later profile omits nationality, and updates it on a confirmed change',async () => {
    const id='nationality-repeat';
    provider({id,account:id,identities:[{isDefault:true,gjm:'US'}]});
    let response=await finish(await start()).expect(302);
    let me=await request(app).get('/api/auth/me').set('Cookie',cookie(response,'arc_session')).expect(200);
    expect(me.body.user.defaultLocale).toBe('en');
    provider({id,account:id});response=await finish(await start()).expect(302);
    me=await request(app).get('/api/auth/me').set('Cookie',cookie(response,'arc_session')).expect(200);
    expect(me.body.user.defaultLocale).toBe('en');
    provider({id,account:id,identities:[{isDefault:true,gjm:'CN'}]});response=await finish(await start()).expect(302);
    me=await request(app).get('/api/auth/me').set('Cookie',cookie(response,'arc_session')).expect(200);
    expect(me.body.user.defaultLocale).toBe('zh');
    expect(await get("SELECT COUNT(*) AS n FROM auth_users WHERE id='jaccount:nationality-repeat'")).toEqual({n:1});
  });
});
