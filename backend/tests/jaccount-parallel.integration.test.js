import { createRequire } from 'node:module';
import request from 'supertest';
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const require = createRequire(import.meta.url);
const app = require('../src/app');
const { createTestDatabaseHarness, get, run } = require('../src/database');
const { createHash } = require('node:crypto');
const envNames = ['JACCOUNT_CLIENT_ID', 'JACCOUNT_CLIENT_SECRET', 'JACCOUNT_REDIRECT_URI'];
let harness, oldEnv;
const stateOf = response => new URL(response.headers.location).searchParams.get('state');
const stateCookies = response => response.headers['set-cookie'].filter(c => c.startsWith('arc_jaccount_state'));
function provider() {
  const fetch = vi.fn(async url => {
    if (url === 'https://jaccount.sjtu.edu.cn/oauth2/token') return { ok: true, json: async () => ({ access_token: 'test-token' }) };
    if (url === 'https://api.sjtu.edu.cn/v1/me/profile') return { ok: true, json: async () => ({ errno: 0, entities: [{ id: 'parallel-campus', account: 'parallel.campus' }] }) };
    throw new Error('Unexpected provider request');
  });
  vi.stubGlobal('fetch', fetch);
  return fetch;
}
describe('independent browser-bound jAccount attempts', () => {
  beforeAll(async () => { harness = createTestDatabaseHarness({ label: 'jaccount-parallel' }); await harness.setup(); });
  beforeEach(() => {
    oldEnv = Object.fromEntries(envNames.map(k => [k, process.env[k]]));
    Object.assign(process.env, { JACCOUNT_CLIENT_ID: 'test-client', JACCOUNT_CLIENT_SECRET: 'test-secret', JACCOUNT_REDIRECT_URI: 'http://localhost:3000/api/auth/jaccount/callback' });
  });
  afterEach(() => { vi.unstubAllGlobals(); for (const [k,v] of Object.entries(oldEnv)) { if(v === undefined) delete process.env[k]; else process.env[k] = v; } });
  afterAll(async () => harness.cleanup());

  it('does not overwrite the first attempt when the same browser starts another login', async () => {
    provider(); const browser = request.agent(app);
    const first = await browser.get('/api/auth/jaccount').expect(302);
    const second = await browser.get('/api/auth/jaccount').expect(302);
    await browser.get('/api/auth/jaccount/callback').query({ state: stateOf(first), code: 'first' }).expect(302).expect('Location', '/paper-upload');
    await browser.get('/api/auth/jaccount/callback').query({ state: stateOf(second), code: 'second' }).expect(302).expect('Location', '/paper-upload');
  });
  it('uses distinct private cookies for parallel attempts', async () => {
    const browser = request.agent(app);
    const first = await browser.get('/api/auth/jaccount').expect(302);
    const second = await browser.get('/api/auth/jaccount').expect(302);
    expect(stateCookies(first)[0].split('=')[0]).not.toBe(stateCookies(second)[0].split('=')[0]);
    expect(stateCookies(first)[0]).toMatch(/HttpOnly/);
    expect(stateCookies(first)[0]).toMatch(/SameSite=Lax/);
    expect(stateCookies(first)[0]).toMatch(/Path=\/api\/auth\/jaccount/);
  });
  it('does not cancel the active attempt when another callback has an invalid state', async () => {
    const fetch = provider(); const browser = request.agent(app);
    const active = await browser.get('/api/auth/jaccount').expect(302);
    await browser.get('/api/auth/jaccount/callback').query({ state: 'invalid', code: 'bad' }).expect(302).expect('Location', '/auth?jaccount_error=state');
    expect(fetch).not.toHaveBeenCalled();
    await browser.get('/api/auth/jaccount/callback').query({ state: stateOf(active), code: 'good' }).expect(302).expect('Location', '/paper-upload');
  });
  it('preserves each report destination when callbacks finish in reverse order', async () => {
    provider(); const browser = request.agent(app);
    const first = await browser.get('/api/auth/jaccount').query({return_to:'/reports/pdf/first?lang=zh'}).expect(302);
    const second = await browser.get('/api/auth/jaccount').query({return_to:'/reports/pdf/second?lang=en'}).expect(302);
    await browser.get('/api/auth/jaccount/callback').query({ state: stateOf(second), code: 'second' }).expect(302).expect('Location', '/reports/pdf/second?lang=en');
    await browser.get('/api/auth/jaccount/callback').query({ state: stateOf(first), code: 'first' }).expect(302).expect('Location', '/reports/pdf/first?lang=zh');
  });
  it('still rejects a callback from another browser before contacting the provider', async () => {
    const fetch = provider(); const start = await request.agent(app).get('/api/auth/jaccount').expect(302);
    await request(app).get('/api/auth/jaccount/callback').query({state:stateOf(start),code:'stolen'}).expect(302).expect('Location','/auth?jaccount_error=state');
    expect(fetch).not.toHaveBeenCalled();
  });
  it('accepts an unexpired legacy cookie already issued before an upgrade', async () => {
    provider(); const start = await request(app).get('/api/auth/jaccount').expect(302);
    await request(app).get('/api/auth/jaccount/callback').set('Cookie','arc_jaccount_state='+stateOf(start))
      .query({state:stateOf(start),code:'legacy'}).expect(302).expect('Location','/paper-upload');
  });
  it('rejects a mismatched scoped cookie even when a matching legacy cookie is present', async () => {
    const fetch = provider(); const start = await request(app).get('/api/auth/jaccount').expect(302);
    const name = stateCookies(start)[0].split('=')[0];
    await request(app).get('/api/auth/jaccount/callback').set('Cookie',name+'='+'x'.repeat(43)+'; arc_jaccount_state='+stateOf(start))
      .query({state:stateOf(start),code:'tampered'}).expect(302).expect('Location','/auth?jaccount_error=state');
    expect(fetch).not.toHaveBeenCalled();
  });
  it('expires only the stale attempt while a newer attempt still completes', async () => {
    provider(); const browser = request.agent(app);
    const stale = await browser.get('/api/auth/jaccount').expect(302);
    const active = await browser.get('/api/auth/jaccount').expect(302);
    await run('UPDATE auth_jaccount_states SET expires_at=? WHERE state_hash=?', ['2000-01-01T00:00:00Z',createHash('sha256').update(stateOf(stale)).digest('hex')]);
    await browser.get('/api/auth/jaccount/callback').query({state:stateOf(stale),code:'stale'}).expect(302).expect('Location','/auth?jaccount_error=state');
    await browser.get('/api/auth/jaccount/callback').query({state:stateOf(active),code:'active'}).expect(302).expect('Location','/paper-upload');
  });
  it('keeps another attempt usable after the provider declines the first one', async () => {
    const fetch = provider(); const browser = request.agent(app);
    const declined = await browser.get('/api/auth/jaccount').expect(302);
    const active = await browser.get('/api/auth/jaccount').expect(302);
    await browser.get('/api/auth/jaccount/callback').query({state:stateOf(declined),error:'access_denied'}).expect(302).expect('Location','/auth?jaccount_error=denied');
    expect(fetch).not.toHaveBeenCalled();
    await browser.get('/api/auth/jaccount/callback').query({state:stateOf(active),code:'active'}).expect(302).expect('Location','/paper-upload');
  });
  it('atomically accepts only one of two simultaneous callbacks for the same attempt', async () => {
    const fetch = provider(); const start = await request(app).get('/api/auth/jaccount').expect(302);
    const cookie = stateCookies(start)[0].split(';')[0];
    const finish = () => request(app).get('/api/auth/jaccount/callback').set('Cookie',cookie).query({state:stateOf(start),code:'once'});
    const before = (await get("SELECT count(*) AS n FROM auth_sessions WHERE user_id='jaccount:parallel-campus'")).n;
    const responses = await Promise.all([finish(),finish()]);
    expect(responses.map(r=>r.status)).toEqual([302,302]);
    expect(responses.map(r=>r.headers.location).sort()).toEqual(['/auth?jaccount_error=state','/paper-upload']);
    expect(fetch).toHaveBeenCalledTimes(2);
    expect((await get("SELECT count(*) AS n FROM auth_sessions WHERE user_id='jaccount:parallel-campus'")).n).toBe(before+1);
  });
  it('does not reuse a completed attempt even if its browser cookie is replayed', async () => {
    const fetch = provider(); const start = await request(app).get('/api/auth/jaccount').expect(302);
    const cookie = stateCookies(start)[0].split(';')[0];
    const finish = () => request(app).get('/api/auth/jaccount/callback').set('Cookie',cookie).query({state:stateOf(start),code:'once'});
    const before = (await get("SELECT count(*) AS n FROM auth_sessions WHERE user_id='jaccount:parallel-campus'")).n;
    await finish().expect(302).expect('Location','/paper-upload');
    await finish().expect(302).expect('Location','/auth?jaccount_error=state');
    expect(fetch).toHaveBeenCalledTimes(2);
    expect((await get("SELECT count(*) AS n FROM auth_sessions WHERE user_id='jaccount:parallel-campus'")).n).toBe(before+1);
  });
});
