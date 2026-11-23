import request from 'supertest';
import { createRequire } from 'node:module';
import { randomUUID } from 'node:crypto';
import { afterAll, beforeAll, beforeEach, describe, expect, it } from 'vitest';

const require = createRequire(import.meta.url);
const app = require('../src/app');
const { createTestDatabaseHarness, get, all, run, closeDb, initializeDatabase, withTransaction } = require('../src/database');
const { createUserSession } = require('../src/auth/sessionService');
const { claimFeedbackAnnouncement } = require('../src/auth/announcementService');
const endpoint = '/api/auth/announcements/feedback/claim';
let harness;
async function login(username = 'student01') {
  const response = await request(app).post('/api/auth/login').send({ username, password: 'ArcDemo123!' }).expect(200);
  return response.headers['set-cookie'].find(value => value.startsWith('arc_session='));
}
function claim(cookie, requestId = randomUUID(), extra = {}) {
  return request(app).post(endpoint).set('Cookie', cookie).send({ request_id: requestId, expected_user_id: 'student01', ...extra });
}

describe('account-scoped feedback announcement', () => {
  beforeAll(async () => { harness = createTestDatabaseHarness({ label:'account-announcement', seedDefault:true }); await harness.setup(); });
  beforeEach(async () => {
    if (await get("SELECT name FROM sqlite_master WHERE name='user_announcement_receipts'")) await run('DELETE FROM user_announcement_receipts');
  });
  afterAll(async () => { await harness.cleanup(); });

  it('requires authentication before allowing an announcement claim', async () => {
    await request(app).post(endpoint).send({request_id:randomUUID()}).expect(401);
  });

  it('shows an existing account once across logout, new sessions and different browsers', async () => {
    const first = await login();
    expect((await claim(first).expect(200)).body.show).toBe(true);
    await request(app).post('/api/auth/logout').set('Cookie',first).expect(204);
    expect((await claim(await login()).expect(200)).body.show).toBe(false);
    expect((await claim(await login()).expect(200)).body.show).toBe(false);
    expect(await get("SELECT count(*) AS n FROM user_announcement_receipts WHERE user_id='student01'")).toEqual({n:1});
  });

  it('covers newly created accounts and jAccount identities with the same receipt policy', async () => {
    for (const id of ['new-announcement-user','jaccount:announcement-campus-person']) {
      await run("INSERT OR IGNORE INTO auth_users(id,username,password_hash,role,scope) VALUES(?,?,?,'STUDENT','SCHOOL')",[id,id,'unused-local-test-hash']);
      const user = {id,username:id,role:'STUDENT',scope:'SCHOOL'};
      const a = await createUserSession(user), b = await createUserSession(user);
      expect((await claim(`arc_session=${a.sessionId}`,randomUUID(),{expected_user_id:id}).expect(200)).body.show).toBe(true);
      expect((await claim(`arc_session=${b.sessionId}`,randomUUID(),{expected_user_id:id}).expect(200)).body.show).toBe(false);
    }
  });

  it.each(['student01','supervisor01','college_admin01','school_admin01'])('supports %s without changing role permissions', async username => {
    expect((await claim(await login(username),randomUUID(),{expected_user_id:username}).expect(200)).body.show).toBe(true);
  });

  it('grants exactly one concurrent token and returns the same result for its retry', async () => {
    const cookie = await login();
    const tokens = Array.from({length:12},()=>randomUUID());
    const replies = await Promise.all(tokens.map(token=>claim(cookie,token).expect(200)));
    const winners = replies.map((response,index)=>({response,index})).filter(value=>value.response.body.show);
    expect(winners).toHaveLength(1);
    const retry = await claim(cookie,tokens[winners[0].index]).expect(200);
    expect(retry.body).toEqual(winners[0].response.body);
    expect(await get('SELECT count(*) AS n FROM user_announcement_receipts')).toEqual({n:1});
    expect(retry.headers['cache-control']).toContain('no-store');
  });

  it('uses authenticated identity, never the requested user ID or announcement version', async () => {
    const a = await login(), b = await login('supervisor01');
    expect((await claim(a,randomUUID(),{user_id:'supervisor01',announcement_id:'forged-version'}).expect(200)).body.show).toBe(true);
    expect(await all('SELECT user_id FROM user_announcement_receipts')).toEqual([{user_id:'student01'}]);
    expect((await claim(b,randomUUID(),{expected_user_id:'supervisor01'}).expect(200)).body.show).toBe(true);
  });

  it('does not consume another account when a different tab replaces the shared session cookie', async () => {
    const b = await login('supervisor01');
    await claim(b,randomUUID(),{expected_user_id:'student01'}).expect(409);
    expect(await all('SELECT * FROM user_announcement_receipts')).toEqual([]);
    expect((await claim(b,randomUUID(),{expected_user_id:'supervisor01'}).expect(200)).body.show).toBe(true);
  });

  it('waits for an unrelated transaction rollback and commits a durable receipt before granting', async () => {
    let release, started;
    const ready = new Promise(resolve=>{started=resolve;});
    const gate = new Promise(resolve=>{release=resolve;});
    const held = withTransaction(async () => { started(); await gate; throw new Error('unrelated rollback'); }).catch(error=>error);
    await ready;
    const pending = claimFeedbackAnnouncement('student01',randomUUID());
    try {
      await new Promise(resolve=>setTimeout(resolve,30));
      expect(await get('SELECT * FROM user_announcement_receipts')).toBeNull();
    } finally { release(); await held; }
    expect((await pending).show).toBe(true);
    expect((await claimFeedbackAnnouncement('student01',randomUUID())).show).toBe(false);
  });

  it('supports trial and jAccount sessions under production authentication policy', async () => {
    const keys = ['ARC_AUTH_MODE','ARC_TRIAL_LOGIN_ENABLED','ARC_TRIAL_LOGIN_ORIGIN','ARC_TRIAL_LOGIN_ORIGINS'];
    const saved = Object.fromEntries(keys.map(key=>[key,process.env[key]]));
    try {
      Object.assign(process.env,{ARC_AUTH_MODE:'jaccount-only',ARC_TRIAL_LOGIN_ENABLED:'1',ARC_TRIAL_LOGIN_ORIGIN:'http://localhost:3000'});
      delete process.env.ARC_TRIAL_LOGIN_ORIGINS;
      require('../src/auth/trialLoginPolicy').trialAttempts.clear();
      const response = await request(app).post('/api/auth/trial-login').set('Host','localhost:3000').set('Origin','http://localhost:3000')
        .send({username:'student01',password:'ArcDemo123!'}).expect(200);
      const cookie = response.headers['set-cookie'].find(value=>value.startsWith('arc_session='));
      expect(cookie).toContain('trial%3A');
      expect((await claim(cookie).expect(200)).body.show).toBe(true);
      expect((await claim(cookie).expect(200)).body.show).toBe(false);
      const id = 'jaccount:production-announcement-person';
      await run("INSERT OR IGNORE INTO auth_users(id,username,password_hash,role,scope) VALUES(?,?,?,'STUDENT','SCHOOL')",[id,id,'unused']);
      const session = await createUserSession({id,username:id,role:'STUDENT',scope:'SCHOOL'});
      expect((await claim(`arc_session=${session.sessionId}`,randomUUID(),{expected_user_id:id}).expect(200)).body.show).toBe(true);
      expect((await claim(`arc_session=${session.sessionId}`,randomUUID(),{expected_user_id:id}).expect(200)).body.show).toBe(false);
    } finally {
      for (const key of keys) { if(saved[key]===undefined) delete process.env[key]; else process.env[key]=saved[key]; }
    }
  });

  it('rejects malformed tokens without consuming a first display', async () => {
    const cookie = await login();
    for (const token of [undefined,'','short','x'.repeat(81),'invalid token with spaces']) {
      await request(app).post(endpoint).set('Cookie',cookie).send({request_id:token}).expect(400);
    }
    expect((await claim(cookie).expect(200)).body.show).toBe(true);
  });

  it('migrates an existing database without altering accounts, sessions or reports and retains receipts on restart', async () => {
    const cookie = await login();
    const snapshots = {};
    for (const table of ['auth_users','auth_sessions','paper_lint_reports']) snapshots[table] = await all(`SELECT * FROM ${table} ORDER BY id`);
    await run('DROP TABLE user_announcement_receipts');
    await closeDb(); await initializeDatabase();
    for (const table of Object.keys(snapshots)) expect(await all(`SELECT * FROM ${table} ORDER BY id`)).toEqual(snapshots[table]);
    expect((await claim(cookie).expect(200)).body.show).toBe(true);
    await closeDb(); await initializeDatabase();
    expect((await claim(cookie).expect(200)).body.show).toBe(false);
  });
});
