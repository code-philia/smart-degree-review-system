const crypto = require('crypto');
const { get, run } = require('../database');
const sessionRepository = require('./sessionRepository');
const { createUserSession } = require('./sessionService');
const { campusUserAllowed } = require('./loginPolicy');
const { campusEmail, notificationEmail } = require('../notifications/emailPolicy');

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

function reportReturnPath(value) {
  return typeof value==='string' && /^\/reports\/pdf\/[A-Za-z0-9-]{1,128}$/.test(value) ? value : null;
}
async function beginLogin(returnTo) {
  const settings = config();
  if (!settings) throw failure('unavailable');
  const state = crypto.randomBytes(32).toString('base64url');
  const now = new Date().toISOString();
  await run('DELETE FROM auth_jaccount_states WHERE expires_at <= ?', [now]);
  await run('INSERT INTO auth_jaccount_states (state_hash, expires_at,return_path) VALUES (?, ?,?)',
    [hashState(state), new Date(Date.now() + STATE_TTL_MS).toISOString(),reportReturnPath(returnTo)]);
  const url = new URL(AUTHORIZE_URL);
  url.search = new URLSearchParams({ response_type: 'code', scope: 'essential',
    client_id: settings.clientId, redirect_uri: settings.redirectUri, state }).toString();
  return { state, url: url.toString() };
}

async function completeLogin({ state, browserState, code, providerError }) {
  if (typeof state !== 'string' || !/^[A-Za-z0-9_-]{43}$/.test(state)
      || typeof browserState !== 'string' || browserState.length !== state.length
      || !crypto.timingSafeEqual(Buffer.from(state), Buffer.from(browserState))) throw failure('state');
  const claimed = await get('DELETE FROM auth_jaccount_states WHERE state_hash = ? AND expires_at > ? RETURNING state_hash,return_path',
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
  const displayName = typeof profile.name === 'string' ? profile.name.trim() || null : null;
  await run(`INSERT INTO auth_users (id, username, display_name, email, password_hash, role, scope)
    VALUES (?, ?, ?, ?, '!jaccount-only', 'STUDENT', 'COLLEGE')
    ON CONFLICT(id) DO UPDATE SET display_name = COALESCE(excluded.display_name, auth_users.display_name),
      email = COALESCE(auth_users.email, excluded.email)`,
  [id, `jaccount:${profile.account}`, displayName, campusEmail(profile)]);
  const user = await sessionRepository.findUserById(id);
  if (!campusUserAllowed(user)) throw failure('forbidden_role');
  if(notificationEmail(user))await run("UPDATE report_email_outbox SET status='pending',next_attempt_at=?,error_code=NULL WHERE user_id=? AND status='blocked' AND error_code='missing_recipient'",[new Date().toISOString(),id]);
  return {...await createUserSession(user),returnTo:reportReturnPath(claimed.return_path)};
}

module.exports = { STATE_COOKIE_NAME, STATE_TTL_MS, isConfigured: () => Boolean(config()), beginLogin, completeLogin };
