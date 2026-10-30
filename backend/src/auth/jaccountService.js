const crypto = require('crypto');
const { get, run } = require('../database');
const sessionRepository = require('./sessionRepository');
const { createUserSession } = require('./sessionService');

const STATE_COOKIE_NAME = 'arc_jaccount_state';
const STATE_TTL_MS = 10 * 60 * 1000;
const AUTHORIZE_URL = 'https://jaccount.sjtu.edu.cn/oauth2/authorize';
const TOKEN_URL = 'https://jaccount.sjtu.edu.cn/oauth2/token';
const PROFILE_URL = 'https://api.sjtu.edu.cn/v1/me/profile';

function config() {
  const clientId = process.env.JACCOUNT_CLIENT_ID?.trim();
  const clientSecret = process.env.JACCOUNT_CLIENT_SECRET?.trim();
  const redirectUri = process.env.JACCOUNT_REDIRECT_URI?.trim();
  if (!clientId || !clientSecret || !redirectUri) return null;
  const callback = new URL(redirectUri);
  if (!['http:', 'https:'].includes(callback.protocol)) return null;
  return { clientId, clientSecret, redirectUri };
}

function failure(code) {
  const error = new Error('jAccount authentication failed');
  error.jaccountCode = code;
  return error;
}

function hashState(state) {
  return crypto.createHash('sha256').update(state).digest('hex');
}

async function beginLogin() {
  const settings = config();
  if (!settings) throw failure('unavailable');
  const state = crypto.randomBytes(32).toString('base64url');
  const now = new Date().toISOString();
  await run('DELETE FROM auth_jaccount_states WHERE expires_at <= ?', [now]);
  await run('INSERT INTO auth_jaccount_states (state_hash, expires_at) VALUES (?, ?)',
    [hashState(state), new Date(Date.now() + STATE_TTL_MS).toISOString()]);
  const url = new URL(AUTHORIZE_URL);
  url.search = new URLSearchParams({ response_type: 'code', scope: 'essential',
    client_id: settings.clientId, redirect_uri: settings.redirectUri, state }).toString();
  return { state, url: url.toString() };
}

async function completeLogin({ state, browserState, code, providerError }) {
  if (typeof state !== 'string' || !/^[A-Za-z0-9_-]{43}$/.test(state)
      || typeof browserState !== 'string' || browserState.length !== state.length
      || !crypto.timingSafeEqual(Buffer.from(state), Buffer.from(browserState))) throw failure('state');
  const claimed = await get('DELETE FROM auth_jaccount_states WHERE state_hash = ? AND expires_at > ? RETURNING state_hash',
    [hashState(state), new Date().toISOString()]);
  if (!claimed) throw failure('state');
  if (providerError) throw failure(providerError === 'access_denied' ? 'denied' : 'provider');
  if (typeof code !== 'string' || !code.trim()) throw failure('provider');
  const settings = config();
  if (!settings) throw failure('unavailable');

  const tokenResponse = await fetch(TOKEN_URL, {
    method: 'POST', redirect: 'error', signal: AbortSignal.timeout(15000),
    headers: { 'Content-Type': 'application/x-www-form-urlencoded', Accept: 'application/json' },
    body: new URLSearchParams({ grant_type: 'authorization_code', code,
      redirect_uri: settings.redirectUri, client_id: settings.clientId, client_secret: settings.clientSecret }).toString(),
  });
  if (!tokenResponse.ok) throw failure('provider');
  const token = await tokenResponse.json();
  if (typeof token.access_token !== 'string' || !token.access_token) throw failure('provider');
  const profileResponse = await fetch(PROFILE_URL, {
    redirect: 'error', signal: AbortSignal.timeout(15000),
    headers: { Authorization: `Bearer ${token.access_token}`, Accept: 'application/json' },
  });
  if (!profileResponse.ok) throw failure('provider');
  const payload = await profileResponse.json();
  const profile = payload.entities?.[0];
  if (payload.errno !== 0 || payload.entities?.length !== 1
      || typeof profile?.id !== 'string' || !profile.id.trim()
      || typeof profile?.account !== 'string' || !profile.account.trim()) throw failure('provider');

  // The campus natural-person ID is stable across account names. Keep campus
  // identities separate from all password users and preserve assigned roles.
  const id = `jaccount:${profile.id}`;
  await run(`INSERT INTO auth_users (id, username, password_hash, role, scope)
    VALUES (?, ?, '!jaccount-only', 'STUDENT', 'COLLEGE')
    ON CONFLICT(id) DO NOTHING`, [id, `jaccount:${profile.account}`]);
  const user = await sessionRepository.findUserById(id);
  return createUserSession(user);
}

module.exports = { STATE_COOKIE_NAME, STATE_TTL_MS, isConfigured: () => Boolean(config()), beginLogin, completeLogin };
