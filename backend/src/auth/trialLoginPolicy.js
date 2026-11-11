const TRIAL_SESSION_PREFIX = 'trial:';
const TRIAL_ACCOUNTS = Object.freeze({
  student01: 'STUDENT', supervisor01: 'SUPERVISOR',
  college_admin01: 'COLLEGE_ADMIN', school_admin01: 'SCHOOL_ADMIN',
});

function trialOrigin() {
  try {
    const url = new URL(process.env.ARC_TRIAL_LOGIN_ORIGIN || '');
    return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password
      && url.pathname === '/' && !url.search && !url.hash ? url.origin : null;
  } catch { return null; }
}
function trialEnabled() {
  return process.env.ARC_TRIAL_LOGIN_ENABLED === '1' && Boolean(trialOrigin());
}
function trialUserAllowed(user) {
  return Boolean(user) && Object.hasOwn(TRIAL_ACCOUNTS, user.username)
    && user.id === user.username && user.role === TRIAL_ACCOUNTS[user.username];
}
function trialSessionAllowed(user, sessionId) {
  return trialEnabled() && typeof sessionId === 'string'
    && sessionId.startsWith(TRIAL_SESSION_PREFIX) && trialUserAllowed(user);
}
function trialLoginRequest(req) {
  const origin = trialOrigin();
  return trialEnabled() && req.is('application/json') && req.headers.origin === origin
    && req.headers.host === new URL(origin).host && req.headers['sec-fetch-site'] !== 'cross-site';
}

// Reserve attempts before password verification so parallel failures cannot
// bypass the limit. Use the TCP peer, never a caller's forwarding headers.
const attempts = new Map();
let nextCleanup = 0;
const WINDOW_MS = 15 * 60 * 1000;
const trialAttempts = {
  clear() { attempts.clear(); nextCleanup = 0; },
  consume(req) {
    const now = Date.now();
    if (now >= nextCleanup) {
      for (const [key, value] of attempts) if (value.until <= now) attempts.delete(key);
      nextCleanup = now + 60_000;
    }
    const peer = req.socket?.remoteAddress || 'unknown';
    const username = typeof req.body?.username === 'string' ? req.body.username.slice(0, 128) : '';
    const buckets = [[`ip:${peer}`, 20], [`account:${peer}:${username}`, 5]];
    for (const [key, limit] of buckets) {
      const value = attempts.get(key);
      if (value?.until > now && value.count >= limit) return Math.ceil((value.until - now) / 1000);
      if (!value && attempts.size >= 10_000) return 60;
    }
    for (const [key] of buckets) {
      let value = attempts.get(key);
      if (!value || value.until <= now) { value = { count: 0, until: now + WINDOW_MS }; attempts.set(key, value); }
      value.count++;
    }
    return 0;
  },
};

module.exports = { TRIAL_ACCOUNTS, TRIAL_SESSION_PREFIX, trialUserAllowed, trialSessionAllowed, trialLoginRequest, trialAttempts };
