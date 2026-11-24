import express from 'express';
import request from 'supertest';
import { createRequire } from 'node:module';
import { createDecipheriv } from 'node:crypto';
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const require = createRequire(import.meta.url);
const { createTestDatabaseHarness, get, all, run, closeDb, initializeDatabase, withTransaction } = require('../src/database');
const { createUserSession } = require('../src/auth/sessionService');
const { getReferenceCredentials, saveReferenceSettings, deleteReferenceSettings } = require('../src/auth/referenceSettingsService');
const endpoint = '/api/auth/reference-settings';
const origin = 'https://app.example.test';
const deploymentKey = Buffer.alloc(32, 17).toString('base64');
const firstKey = 'personal-openalex-secret-1234';
const secondKey = 'replacement-openalex-secret-5678';
const envKeys = ['REFERENCE_SETTINGS_ENCRYPTION_KEY', 'OPENALEX_API_KEY', 'OPENALEX_API_KEYS',
  'APP_PUBLIC_URL', 'JACCOUNT_REDIRECT_URI', 'ARC_CORS_ORIGIN', 'ARC_TRIAL_LOGIN_ENABLED',
  'ARC_TRIAL_LOGIN_ORIGIN', 'ARC_TRIAL_LOGIN_ORIGINS', 'ARC_AUTH_MODE', 'NODE_ENV', 'REFERENCE_SETTINGS_ALLOW_INSECURE_DEVELOPMENT', 'PAPER_COMPILER_EVIDENCE_CONFIG'];
const savedEnv = Object.fromEntries(envKeys.map(key => [key, process.env[key]]));
let app, harness, aliceCookie, bobCookie;

function authenticatedProviderResponse(input) {
  const url = new URL(input);
  const api_key = url.searchParams.get('api_key');
  if (url.origin === 'https://api.openalex.org' && url.pathname === '/rate-limit') {
    return Response.json({ api_key, rate_limit: { daily_budget_usd: 1, daily_used_usd: 0,
      daily_remaining_usd: 1, resets_at: '2026-11-26T00:00:00.000Z', resets_in_seconds: 3600 } });
  }
  if (url.origin === 'https://serpapi.com' && url.pathname === '/account.json') {
    return Response.json({ account_id: 'test-account', api_key, account_email: 'test@example.test',
      account_status: 'Active', total_searches_left: 0 });
  }
  throw new Error('Unexpected provider verification destination');
}

function read(cookie = aliceCookie) {
  return request(app).get(endpoint).set('Cookie', cookie);
}

function write(method = 'put', body = {}, cookie = aliceCookie, headers = {}) {
  const pending = request(app)[method](endpoint).set('Cookie', cookie)
    .set('Host', 'app.example.test').set('Origin', origin);
  for (const [name, value] of Object.entries(headers)) {
    if (value === null) pending.unset(name); else pending.set(name, value);
  }
  return pending.send({ expected_user_id: 'jaccount:alice', ...body });
}

describe('private account reference settings', () => {
  beforeAll(async () => {
    harness = createTestDatabaseHarness({ label: 'reference-settings' });
    await harness.setup();
    for (const id of ['jaccount:alice', 'jaccount:bob']) {
      await run("INSERT INTO auth_users(id,username,password_hash,role,scope) VALUES(?,?,?,'STUDENT','SCHOOL')", [id, id, 'unused']);
    }
    aliceCookie = `arc_session=${encodeURIComponent((await createUserSession({ id: 'jaccount:alice' })).sessionId)}`;
    bobCookie = `arc_session=${encodeURIComponent((await createUserSession({ id: 'jaccount:bob' })).sessionId)}`;
    app = express();
    app.use(endpoint, require('../src/auth/referenceSettingsRoutes'));
  });

  beforeEach(async () => {
    vi.stubGlobal('fetch', vi.fn(async input => authenticatedProviderResponse(input)));
    for (const key of envKeys) delete process.env[key];
    Object.assign(process.env, { NODE_ENV: 'test', APP_PUBLIC_URL: origin, REFERENCE_SETTINGS_ENCRYPTION_KEY: deploymentKey,
      PAPER_COMPILER_EVIDENCE_CONFIG: `${harness.dbPath}.absent-evidence-config` });
    if (await get("SELECT name FROM sqlite_master WHERE name='user_reference_settings'")) {
      await run('DELETE FROM user_reference_settings');
    }
  });

  afterEach(() => vi.unstubAllGlobals());

  afterAll(async () => {
    for (const key of envKeys) {
      if (savedEnv[key] === undefined) delete process.env[key]; else process.env[key] = savedEnv[key];
    }
    await harness.cleanup();
  });

  it('adds credential storage to existing databases without rewriting users, sessions or reports', async () => {
    const snapshots = {};
    for (const table of ['auth_users', 'auth_sessions', 'paper_lint_reports']) snapshots[table] = await all(`SELECT * FROM ${table} ORDER BY id`);
    expect(await get("SELECT name FROM sqlite_master WHERE name='user_reference_settings'")).toEqual({ name: 'user_reference_settings' });
    await run('DROP TABLE user_reference_settings');
    await closeDb();
    await initializeDatabase();
    expect(await get("SELECT name FROM sqlite_master WHERE name='user_reference_settings'")).toEqual({ name: 'user_reference_settings' });
    for (const table of Object.keys(snapshots)) expect(await all(`SELECT * FROM ${table} ORDER BY id`)).toEqual(snapshots[table]);
  });

  it('requires an authenticated session for reads, saves and deletes', async () => {
    for (const method of ['get', 'put', 'delete']) await request(app)[method](endpoint).send({ api_key: firstKey }).expect(401);
    await request(app).get(endpoint).set('Cookie', 'arc_session=expired-or-forged').expect(401);
  });

  it('returns only private noncached status when no personal key exists', async () => {
    const response = await read().expect(200);
    expect(response.body).toEqual({ configured: false, key_hint: null, storage_available: true, serpapi_configured: false, serpapi_key_hint: null });
    expect(response.headers['cache-control']).toContain('no-store');
  });

  it('encrypts a saved key at rest and only returns its masked suffix', async () => {
    const saved = await write('put', { api_key: firstKey }).expect(200);
    expect(saved.body).toEqual({ configured: true, key_hint: '••••1234', storage_available: true, serpapi_configured: false, serpapi_key_hint: null });
    const row = await get('SELECT * FROM user_reference_settings WHERE user_id=?', ['jaccount:alice']);
    expect(row).not.toBeNull();
    expect(JSON.stringify(row)).not.toContain(firstKey);
    expect(JSON.stringify(row)).not.toContain(deploymentKey);
    const [version, iv, tag, ciphertext] = row.encrypted_api_key.split('.');
    expect(version).toBe('v1');
    const decipher = createDecipheriv('aes-256-gcm', Buffer.from(deploymentKey, 'base64'), Buffer.from(iv, 'base64'));
    decipher.setAAD(Buffer.from('["jaccount:alice","openalex"]'));
    decipher.setAuthTag(Buffer.from(tag, 'base64'));
    expect(Buffer.concat([decipher.update(Buffer.from(ciphertext, 'base64')), decipher.final()]).toString()).toBe(firstKey);
    expect((await read().expect(200)).body).toEqual(saved.body);
    expect(JSON.stringify(saved.body)).not.toContain(firstKey);
  });

  it('isolates account status and rejects requests whose cookie switched to another account', async () => {
    await write('put', { api_key: firstKey }).expect(200);
    expect((await read(bobCookie).expect(200)).body.configured).toBe(false);
    for (const method of ['put', 'delete']) {
      const response = await write(method, { api_key: secondKey }, bobCookie).expect(409);
      expect(response.body.error_code).toBe('account_changed');
    }
    expect((await read().expect(200)).body.key_hint).toBe('••••1234');
    await write('put', { api_key: secondKey, expected_user_id: 'jaccount:bob' }, bobCookie).expect(200);
    expect((await read(bobCookie).expect(200)).body.key_hint).toBe('••••5678');
    expect((await read().expect(200)).body.key_hint).toBe('••••1234');
  });

  it('requires an explicit account precondition for each write', async () => {
    for (const expected_user_id of [undefined, null, '', {}, 'jaccount:bob']) {
      await write('put', { api_key: firstKey, expected_user_id }).expect(409);
      await write('delete', { expected_user_id }).expect(409);
    }
    expect(await all('SELECT * FROM user_reference_settings')).toEqual([]);
  });

  it('replaces keys with fresh ciphertext and deletes only the current account key', async () => {
    await write('put', { api_key: firstKey }).expect(200);
    const previous = await get('SELECT encrypted_api_key FROM user_reference_settings WHERE user_id=?', ['jaccount:alice']);
    await write('put', { api_key: firstKey }).expect(200);
    expect(await get('SELECT encrypted_api_key FROM user_reference_settings WHERE user_id=?', ['jaccount:alice'])).not.toEqual(previous);
    await write('put', { api_key: secondKey }).expect(200);
    await write('put', { api_key: firstKey, expected_user_id: 'jaccount:bob' }, bobCookie).expect(200);
    expect((await write('delete').expect(200)).body).toEqual({ configured: false, key_hint: null, storage_available: true, serpapi_configured: false, serpapi_key_hint: null });
    await write('delete').expect(200);
    expect((await read(bobCookie).expect(200)).body.key_hint).toBe('••••1234');
    expect(await all('SELECT user_id FROM user_reference_settings')).toEqual([{ user_id: 'jaccount:bob' }]);
  });

  it('rejects invalid API keys without echoing submitted secrets or changing stored data', async () => {
    await write('put', { api_key: firstKey }).expect(200);
    for (const api_key of [undefined, null, {}, 12, '', '  ', 'bad key', 'bad\nkey', 'x'.repeat(513), '密钥']) {
      const response = await write('put', { api_key }).expect(400);
      expect(response.body.error_code).toBe('invalid_api_key');
      expect(response.body.api_key).toBeUndefined();
      expect(JSON.stringify(response.body)).not.toContain(firstKey);
    }
    expect((await read().expect(200)).body.key_hint).toBe('••••1234');
  });

  it('bounds request bodies and sanitizes malformed JSON errors', async () => {
    const oversized = await write('put', { api_key: 'private-body-secret'.repeat(300) }).expect(413);
    expect(oversized.text).not.toContain('private-body-secret');
    const malformed = await request(app).put(endpoint).set('Cookie', aliceCookie).set('Host', 'app.example.test')
      .set('Origin', origin).set('Content-Type', 'application/json').send('{"api_key":"private-malformed-secret"').expect(400);
    expect(malformed.text).not.toContain('private-malformed-secret');
  });

  it('accepts writes only from a configured exact same origin and ignores spoofed forwarded headers', async () => {
    for (const headers of [
      { Origin: 'https://evil.example' }, { Origin: 'http://app.example.test' }, { Origin: 'null' }, { Origin: null },
      { Origin: 'https://app.example.test.evil.example' }, { 'Sec-Fetch-Site': 'cross-site' },
      { Origin: 'https://evil.example', Host: 'evil.example' },
      { Origin: origin, Host: 'evil.example', 'X-Forwarded-Host': 'app.example.test', 'X-Forwarded-Proto': 'https' },
    ]) {
      for (const method of ['put', 'delete']) await write(method, { api_key: firstKey }, aliceCookie, headers).expect(403);
    }
    expect(await all('SELECT * FROM user_reference_settings')).toEqual([]);
    await write('put', { api_key: firstKey }).expect(200);
  });

  it('allows configured deployment entry points and fails closed without trusted production configuration', async () => {
    delete process.env.APP_PUBLIC_URL;
    process.env.NODE_ENV = 'production';
    await write('put', { api_key: firstKey }).expect(403);
    process.env.JACCOUNT_REDIRECT_URI = `${origin}/api/auth/jaccount/callback`;
    await write('put', { api_key: firstKey }).expect(200);
    delete process.env.JACCOUNT_REDIRECT_URI;
    process.env.ARC_CORS_ORIGIN = origin;
    await write('delete').expect(200);
    delete process.env.ARC_CORS_ORIGIN;
    process.env.ARC_TRIAL_LOGIN_ENABLED = '1';
    process.env.ARC_TRIAL_LOGIN_ORIGINS = origin;
    await write('put', { api_key: firstKey }).expect(200);
  });

  it('disables saving safely without valid encryption material but still permits deletion', async () => {
    await write('put', { api_key: firstKey }).expect(200);
    const row = await get('SELECT * FROM user_reference_settings');
    for (const key of [undefined, '', 'private-invalid-deployment-key', Buffer.alloc(31).toString('base64'), deploymentKey.slice(0, -1)]) {
      if (key === undefined) delete process.env.REFERENCE_SETTINGS_ENCRYPTION_KEY;
      else process.env.REFERENCE_SETTINGS_ENCRYPTION_KEY = key;
      const response = await write('put', { api_key: secondKey }).expect(503);
      expect(response.body.error_code).toBe('storage_unavailable');
      expect(response.text).not.toContain(secondKey);
      const status = (await read().expect(200)).body;
      expect(status.configured).toBe(true);
      expect(status.storage_available).toBe(false);
      expect(status.key_hint).toBeNull();
      expect(await get('SELECT * FROM user_reference_settings')).toEqual(row);
    }
    expect((await write('delete').expect(200)).body).toEqual({ configured: false, key_hint: null, storage_available: false, serpapi_configured: false, serpapi_key_hint: null });
  });

  it('provides decrypted credentials only to private runtime callers for their own account', async () => {
    process.env.OPENALEX_API_KEYS = 'platform-one,platform-two,platform-one';
    await write('put', { api_key: firstKey }).expect(200);
    await write('put', { api_key: secondKey, expected_user_id: 'jaccount:bob' }, bobCookie).expect(200);
    expect(await getReferenceCredentials('jaccount:alice')).toEqual({ personalKey: firstKey, serpapiKey: null, serpapi_credential_status: 'not_configured',
      platformKeys: ['platform-one', 'platform-two'], credential_status: 'available' });
    expect(await getReferenceCredentials('jaccount:bob')).toEqual({ personalKey: secondKey, serpapiKey: null, serpapi_credential_status: 'not_configured',
      platformKeys: ['platform-one', 'platform-two'], credential_status: 'available' });
    expect((await read().expect(200)).text).not.toContain('platform-one');
    await write('delete').expect(200);
    expect(await getReferenceCredentials('jaccount:alice')).toEqual({ personalKey: null, serpapiKey: null, serpapi_credential_status: 'not_configured',
      platformKeys: ['platform-one', 'platform-two'], credential_status: 'not_configured' });
  });

  it('uses the legacy platform key when no platform list is configured and handles no-key operation', async () => {
    expect(await getReferenceCredentials('jaccount:alice')).toEqual({ personalKey: null, platformKeys: [], credential_status: 'not_configured', serpapiKey: null, serpapi_credential_status: 'not_configured' });
    process.env.OPENALEX_API_KEY = 'legacy-platform-secret';
    expect((await getReferenceCredentials('jaccount:alice')).platformKeys).toEqual(['legacy-platform-secret']);
    process.env.OPENALEX_API_KEYS = 'new-platform-one;new-platform-two\nnew-platform-one';
    expect((await getReferenceCredentials('jaccount:alice')).platformKeys).toEqual(['new-platform-one', 'new-platform-two']);
    expect((await read().expect(200)).text).not.toContain('platform');
  });

  it('authenticates ciphertext to its original account instead of using copied credentials', async () => {
    process.env.OPENALEX_API_KEY = 'platform-fallback';
    await write('put', { api_key: firstKey }).expect(200);
    const row = await get('SELECT encrypted_api_key FROM user_reference_settings WHERE user_id=?', ['jaccount:alice']);
    await run('INSERT INTO user_reference_settings(user_id,encrypted_api_key) VALUES(?,?)', ['jaccount:bob', row.encrypted_api_key]);
    expect(await getReferenceCredentials('jaccount:bob')).toEqual({ personalKey: null, serpapiKey: null, serpapi_credential_status: 'not_configured',
      platformKeys: ['platform-fallback'], credential_status: 'unavailable' });
    expect((await read(bobCookie).expect(200)).body).toEqual({ configured: true, key_hint: null, storage_available: false, serpapi_configured: false, serpapi_key_hint: null });
    expect((await getReferenceCredentials('jaccount:alice')).personalKey).toBe(firstKey);
  });

  it('reports deployment key loss safely while preserving platform fallback and allowing replacement', async () => {
    process.env.OPENALEX_API_KEY = 'platform-fallback';
    await write('put', { api_key: firstKey }).expect(200);
    for (const key of [undefined, Buffer.alloc(32, 42).toString('base64')]) {
      if (key === undefined) delete process.env.REFERENCE_SETTINGS_ENCRYPTION_KEY;
      else process.env.REFERENCE_SETTINGS_ENCRYPTION_KEY = key;
      expect(await getReferenceCredentials('jaccount:alice')).toEqual({ personalKey: null, serpapiKey: null, serpapi_credential_status: 'not_configured',
        platformKeys: ['platform-fallback'], credential_status: 'unavailable' });
      expect((await read().expect(200)).body).toEqual({ configured: true, key_hint: null, storage_available: false, serpapi_configured: false, serpapi_key_hint: null });
    }
    await write('put', { api_key: secondKey }).expect(200);
    expect((await getReferenceCredentials('jaccount:alice')).personalKey).toBe(secondKey);
  });

  it('never returns malformed, tampered or plaintext stored credentials through any interface', async () => {
    await write('put', { api_key: firstKey }).expect(200);
    const { encrypted_api_key: encrypted } = await get('SELECT encrypted_api_key FROM user_reference_settings');
    for (const value of [firstKey, 'not.an.envelope', encrypted.replace('v1.', 'v2.'), encrypted.slice(0, -4), 'x'.repeat(2049)]) {
      await run('UPDATE user_reference_settings SET encrypted_api_key=?', [value]);
      const credentials = await getReferenceCredentials('jaccount:alice');
      expect(credentials.personalKey).toBeNull();
      expect(credentials.credential_status).toBe('unavailable');
      const response = await read().expect(200);
      expect(response.body).toEqual({ configured: true, key_hint: null, storage_available: false, serpapi_configured: false, serpapi_key_hint: null });
      expect(response.text).not.toContain(firstKey);
    }
  });

  it('persists encrypted credentials across database reopen and removes rows when an account is deleted', async () => {
    await write('put', { api_key: firstKey }).expect(200);
    await closeDb();
    await initializeDatabase();
    expect((await getReferenceCredentials('jaccount:alice')).personalKey).toBe(firstKey);
    await run("INSERT INTO auth_users(id,username,password_hash,role,scope) VALUES('jaccount:deleted','deleted','unused','STUDENT','SCHOOL')");
    await saveReferenceSettings('jaccount:deleted', { api_key: secondKey });
    await run("DELETE FROM auth_users WHERE id='jaccount:deleted'");
    expect(await get("SELECT * FROM user_reference_settings WHERE user_id='jaccount:deleted'")).toBeNull();
    expect((await getReferenceCredentials('jaccount:alice')).personalKey).toBe(firstKey);
  });

  it('waits for unrelated transaction rollback before acknowledging a durable save or deletion', async () => {
    for (const operation of ['save', 'delete']) {
      let unlock, markReady;
      const gate = new Promise(resolve => { unlock = resolve; });
      const ready = new Promise(resolve => { markReady = resolve; });
      const rollback = withTransaction(async () => { markReady(); await gate; throw new Error('unrelated rollback'); }).catch(error => error);
      await ready;
      const pending = operation === 'save' ? saveReferenceSettings('jaccount:alice', { api_key: firstKey }) : deleteReferenceSettings('jaccount:alice');
      try {
        await new Promise(resolve => setTimeout(resolve, 20));
      } finally {
        unlock();
        await rollback;
      }
      await pending;
      expect((await read().expect(200)).body.configured).toBe(operation === 'save');
    }
  });

  it('sanitizes storage failures while keeping runtime fallback available', async () => {
    process.env.OPENALEX_API_KEY = 'private-platform-fallback';
    await run('DROP TABLE user_reference_settings');
    try {
      expect(await getReferenceCredentials('jaccount:alice')).toEqual({ personalKey: null, serpapiKey: null, serpapi_credential_status: 'storage_unavailable',
        platformKeys: ['private-platform-fallback'], credential_status: 'storage_unavailable' });
      for (const method of ['get', 'put', 'delete']) {
        const response = await (method === 'get' ? read() : write(method, { api_key: firstKey })).expect(503);
        expect(response.body.error_code).toBe('storage_unavailable');
        expect(response.text).not.toContain(firstKey);
        expect(response.text).not.toContain('private-platform-fallback');
        expect(response.text).not.toContain('SQLITE');
        expect(response.text).not.toContain('user_reference_settings');
      }
    } finally {
      await closeDb();
      await initializeDatabase();
    }
  });

  it('saves either provider independently and preserves the other when replacing one key', async () => {
    const serpapiKey = 'personal-serpapi-secret-7890';
    const first = await write('put', { serpapi_key: serpapiKey }).expect(200);
    expect(first.body).toEqual({ configured: false, key_hint: null, serpapi_configured: true, serpapi_key_hint: '••••7890', storage_available: true });
    expect((await getReferenceCredentials('jaccount:alice')).serpapiKey).toBe(serpapiKey);
    await write('put', { api_key: firstKey }).expect(200);
    expect((await getReferenceCredentials('jaccount:alice')).serpapiKey).toBe(serpapiKey);
    await write('put', { serpapi_key: secondKey }).expect(200);
    const credentials = await getReferenceCredentials('jaccount:alice');
    expect(credentials.personalKey).toBe(firstKey);
    expect(credentials.serpapiKey).toBe(secondKey);
    expect(credentials.serpapi_credential_status).toBe('available');
    const status = await read().expect(200);
    expect(status.body).toEqual({ configured: true, key_hint: '••••1234', serpapi_configured: true, serpapi_key_hint: '••••5678', storage_available: true });
    for (const secret of [firstKey, secondKey, serpapiKey]) {
      expect(status.text).not.toContain(secret);
      expect(JSON.stringify(await all('SELECT * FROM user_reference_settings'))).not.toContain(secret);
    }
  });

  it('atomically saves both provider keys and rejects an invalid field without partial updates', async () => {
    await write('put', { api_key: firstKey, serpapi_key: secondKey }).expect(200);
    const rows = await all('SELECT * FROM user_reference_settings ORDER BY provider');
    for (const serpapi_key of [null, 7, {}, '', 'bad\nkey', 'x'.repeat(513)]) {
      const response = await write('put', { api_key: 'changed-openalex-secret', serpapi_key }).expect(400);
      expect(response.body.error_code).toBe('invalid_serpapi_key');
      expect(response.text).not.toContain('changed-openalex-secret');
      expect(await all('SELECT * FROM user_reference_settings ORDER BY provider')).toEqual(rows);
    }
  });

  it.each([
    ['api_key', 'openalex', 'invalid_api_key'],
    ['serpapi_key', 'serpapi', 'invalid_serpapi_key'],
  ])('verifies %s with its provider before saving and preserves existing ciphertext on rejection', async (field, provider, code) => {
    await write('put', { api_key: firstKey, serpapi_key: secondKey }).expect(200);
    const rows = await all('SELECT * FROM user_reference_settings ORDER BY provider');
    process.env.OPENALEX_API_KEY = 'platform-key-must-not-validate-personal-key';
    globalThis.fetch = vi.fn(async () => Response.json({ error: 'private-provider-secret' }, { status: 401 }));
    const response = await write('put', { [field]: 'invalid-personal-candidate' }).expect(400);
    expect(response.body.error_code).toBe(code);
    expect(response.text).not.toContain('private-provider-secret');
    expect(response.text).not.toContain('invalid-personal-candidate');
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
    const target = new URL(globalThis.fetch.mock.calls[0][0]);
    expect(target.origin).toBe(provider === 'openalex' ? 'https://api.openalex.org' : 'https://serpapi.com');
    expect(target.searchParams.get('api_key')).toBe('invalid-personal-candidate');
    expect(await all('SELECT * FROM user_reference_settings ORDER BY provider')).toEqual(rows);
    const credentials = await getReferenceCredentials('jaccount:alice');
    expect(credentials.personalKey).toBe(firstKey);
    expect(credentials.serpapiKey).toBe(secondKey);
  });

  it.each([
    ['api_key', 'openalex_verification_unavailable'],
    ['serpapi_key', 'serpapi_verification_unavailable'],
  ])('reports a temporary provider failure for %s without replacing saved keys', async (field, code) => {
    await write('put', { api_key: firstKey, serpapi_key: secondKey }).expect(200);
    const rows = await all('SELECT * FROM user_reference_settings ORDER BY provider');
    globalThis.fetch = vi.fn(async () => Response.json({ error: 'private-provider-secret' }, { status: 429 }));
    const response = await write('put', { [field]: 'replacement-candidate' }).expect(503);
    expect(response.body.error_code).toBe(code);
    expect(response.text).not.toContain('private-provider-secret');
    expect(response.text).not.toContain('replacement-candidate');
    expect(await all('SELECT * FROM user_reference_settings ORDER BY provider')).toEqual(rows);
  });

  it('validates both providers before persisting either update', async () => {
    await write('put', { api_key: firstKey, serpapi_key: secondKey }).expect(200);
    const rows = await all('SELECT * FROM user_reference_settings ORDER BY provider');
    globalThis.fetch = vi.fn(async input => new URL(input).hostname === 'serpapi.com'
      ? Response.json({ error: 'Invalid private credential' }, { status: 403 }) : authenticatedProviderResponse(input));
    const response = await write('put', { api_key: 'valid-new-openalex', serpapi_key: 'invalid-new-serpapi' }).expect(400);
    expect(response.body.error_code).toBe('invalid_serpapi_key');
    expect(await all('SELECT * FROM user_reference_settings ORDER BY provider')).toEqual(rows);
  });

  it('avoids provider verification before authentication, account and local credential preconditions pass', async () => {
    await request(app).put(endpoint).send({ api_key: firstKey }).expect(401);
    await write('put', { api_key: firstKey }, bobCookie).expect(409);
    await write('put', { api_key: firstKey }, aliceCookie, { Origin: 'https://evil.example' }).expect(403);
    await write('put', { api_key: firstKey, serpapi_key: 'bad key' }).expect(400);
    expect(globalThis.fetch).not.toHaveBeenCalled();
    expect(await all('SELECT * FROM user_reference_settings')).toEqual([]);
  });

  it('deletes only the selected provider and rejects unrecognized selectors', async () => {
    await write('put', { api_key: firstKey, serpapi_key: secondKey }).expect(200);
    await write('delete', { provider: 'serpapi' }).expect(200);
    let credentials = await getReferenceCredentials('jaccount:alice');
    expect(credentials.personalKey).toBe(firstKey);
    expect(credentials.serpapiKey).toBeNull();
    await write('put', { serpapi_key: secondKey }).expect(200);
    await write('delete').expect(200);
    credentials = await getReferenceCredentials('jaccount:alice');
    expect(credentials.personalKey).toBeNull();
    expect(credentials.serpapiKey).toBe(secondKey);
    for (const provider of ['other', '', null, {}, ['serpapi']]) {
      expect((await write('delete', { provider }).expect(400)).body.error_code).toBe('invalid_provider');
    }
    expect((await getReferenceCredentials('jaccount:alice')).serpapiKey).toBe(secondKey);
  });

  it('prevents using a ciphertext for another provider or account', async () => {
    await write('put', { api_key: firstKey, serpapi_key: secondKey }).expect(200);
    const row = await get("SELECT encrypted_api_key FROM user_reference_settings WHERE user_id=? AND provider='openalex'", ['jaccount:alice']);
    await run("UPDATE user_reference_settings SET encrypted_api_key=? WHERE provider='serpapi'", [row.encrypted_api_key]);
    let credentials = await getReferenceCredentials('jaccount:alice');
    expect(credentials.personalKey).toBe(firstKey);
    expect(credentials.serpapiKey).toBeNull();
    expect(credentials.serpapi_credential_status).toBe('unavailable');
    await write('put', { serpapi_key: secondKey }).expect(200);
    const serpapiRow = await get("SELECT encrypted_api_key FROM user_reference_settings WHERE user_id=? AND provider='serpapi'", ['jaccount:alice']);
    await run('INSERT INTO user_reference_settings(user_id,provider,encrypted_api_key) VALUES(?,?,?)', ['jaccount:bob', 'serpapi', serpapiRow.encrypted_api_key]);
    credentials = await getReferenceCredentials('jaccount:bob');
    expect(credentials.serpapiKey).toBeNull();
    expect(credentials.serpapi_credential_status).toBe('unavailable');
    expect((await getReferenceCredentials('jaccount:alice')).serpapiKey).toBe(secondKey);
  });

  it('requires the account precondition for SerpAPI writes and never borrows another account key', async () => {
    await write('put', { serpapi_key: secondKey }).expect(200);
    expect((await read(bobCookie).expect(200)).body.serpapi_configured).toBe(false);
    expect((await getReferenceCredentials('jaccount:bob')).serpapiKey).toBeNull();
    await write('put', { serpapi_key: firstKey }, bobCookie).expect(409);
    await write('delete', { provider: 'serpapi' }, bobCookie).expect(409);
    expect((await getReferenceCredentials('jaccount:alice')).serpapiKey).toBe(secondKey);
    delete process.env.REFERENCE_SETTINGS_ENCRYPTION_KEY;
    expect((await getReferenceCredentials('jaccount:alice')).serpapiKey).toBeNull();
    expect((await read().expect(200)).body).toEqual({ configured: false, key_hint: null, serpapi_configured: true, serpapi_key_hint: null, storage_available: false });
    await write('delete', { provider: 'serpapi' }).expect(200);
  });

  it('trims pasted tokens, accepts the size boundary and completely masks short keys', async () => {
    await write('put', { api_key: `  ${firstKey}  `, serpapi_key: 'x'.repeat(512) }).expect(200);
    expect((await getReferenceCredentials('jaccount:alice')).personalKey).toBe(firstKey);
    expect((await getReferenceCredentials('jaccount:alice')).serpapiKey).toBe('x'.repeat(512));
    const response = await write('put', { api_key: 'tiny', serpapi_key: 'key' }).expect(200);
    expect(response.body.key_hint).toBe('••••');
    expect(response.body.serpapi_key_hint).toBe('••••');
    expect(response.text).not.toContain('tiny');
  });

  it('rolls back both provider changes and sanitizes driver errors if the second write fails', async () => {
    await write('put', { api_key: firstKey, serpapi_key: secondKey }).expect(200);
    await run(`CREATE TRIGGER reference_settings_test_rejection BEFORE INSERT ON user_reference_settings
      WHEN NEW.provider='serpapi' BEGIN SELECT RAISE(ABORT,'private-driver-secret'); END`);
    try {
      const response = await write('put', { api_key: 'changed-openalex', serpapi_key: 'changed-serpapi' }).expect(503);
      expect(response.text).not.toContain('private-driver-secret');
      expect(response.text).not.toContain('changed-openalex');
      const credentials = await getReferenceCredentials('jaccount:alice');
      expect(credentials.personalKey).toBe(firstKey);
      expect(credentials.serpapiKey).toBe(secondKey);
    } finally {
      await run('DROP TRIGGER reference_settings_test_rejection');
    }
  });

  it('rejects production HTTP secret saves and disables entry without changing runtime credentials', async () => {
    process.env.NODE_ENV = 'production';
    await write('put', { api_key: firstKey, serpapi_key: secondKey }).expect(200);
    process.env.APP_PUBLIC_URL = 'http://app.example.test';
    const rows = await all('SELECT * FROM user_reference_settings ORDER BY provider');
    const response = await write('put', { api_key: 'http-submitted-secret', serpapi_key: 'http-serpapi-secret' }, aliceCookie,
      { Origin: 'http://app.example.test', 'X-Forwarded-Proto': 'https' }).expect(403);
    expect(response.body.error_code).toBe('secure_transport_required');
    expect(response.text).not.toContain('http-submitted-secret');
    expect(await all('SELECT * FROM user_reference_settings ORDER BY provider')).toEqual(rows);
    const status = await read().set('Host', 'app.example.test').expect(200);
    expect(status.body.secure_transport_required).toBe(true);
    expect(status.body.storage_available).toBe(false);
    expect((await getReferenceCredentials('jaccount:alice')).personalKey).toBe(firstKey);
    expect((await getReferenceCredentials('jaccount:alice')).serpapiKey).toBe(secondKey);
    await write('delete', {}, aliceCookie, { Origin: 'http://app.example.test' }).expect(200);
    expect((await getReferenceCredentials('jaccount:alice')).personalKey).toBeNull();
    expect((await getReferenceCredentials('jaccount:alice')).serpapiKey).toBe(secondKey);
  });

  it('accepts trusted HTTPS browser origins behind an HTTP proxy without relying on forwarded headers', async () => {
    process.env.NODE_ENV = 'production';
    await write('put', { api_key: firstKey }, aliceCookie, { 'X-Forwarded-Proto': 'http' }).expect(200);
    const status = await read().set('Host', 'app.example.test').expect(200);
    expect(status.body.storage_available).toBe(true);
    expect(status.body.secure_transport_required).not.toBe(true);
    const downgraded = await read().set('Host', 'app.example.test').set('Origin', 'http://app.example.test').expect(200);
    expect(downgraded.body.secure_transport_required).toBe(true);
    expect(downgraded.body.storage_available).toBe(false);
  });

  it('retains local development HTTP saves on actual loopback connections', async () => {
    delete process.env.APP_PUBLIC_URL;
    await write('put', { api_key: firstKey }, aliceCookie, { Host: '127.0.0.1:3000', Origin: 'http://127.0.0.1:3000' }).expect(200);
    const status = await read().set('Host', '127.0.0.1:3000').expect(200);
    expect(status.body.storage_available).toBe(true);
    expect(status.body.secure_transport_required).not.toBe(true);
  });

  it('allows the explicit HTTP development exception only for exact configured trusted origins', async () => {
    process.env.NODE_ENV = 'production';
    process.env.APP_PUBLIC_URL = 'http://app.example.test';
    process.env.REFERENCE_SETTINGS_ALLOW_INSECURE_DEVELOPMENT = '1';
    await write('put', { api_key: firstKey, serpapi_key: secondKey }, aliceCookie, { Origin: 'http://app.example.test' }).expect(200);
    const status = await read().set('Host', 'app.example.test').expect(200);
    expect(status.body.storage_available).toBe(true);
    expect(status.body.secure_transport_required).not.toBe(true);
    await write('put', { api_key: 'wrong-host-secret' }, aliceCookie, { Origin: 'http://evil.example', Host: 'evil.example' }).expect(403);
    const untrusted = await read().set('Host', 'evil.example').expect(200);
    expect(untrusted.body.storage_available).toBe(false);
    expect(untrusted.body.secure_transport_required).toBe(true);
    expect((await getReferenceCredentials('jaccount:alice')).personalKey).toBe(firstKey);
  });
});
