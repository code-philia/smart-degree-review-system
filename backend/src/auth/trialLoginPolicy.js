const TRIAL_SESSION_PREFIX = 'trial:';
const TRIAL_ACCOUNTS = Object.freeze({
  student01: 'STUDENT', supervisor01: 'SUPERVISOR',
  college_admin01: 'COLLEGE_ADMIN', school_admin01: 'SCHOOL_ADMIN',
});

function trialOrigins() {
  try {
    const configured = process.env.ARC_TRIAL_LOGIN_ORIGINS;
    const values = configured === undefined
      ? [process.env.ARC_TRIAL_LOGIN_ORIGIN || ''] : configured.split(',');
    const origins = values.map(value => {
      const url = new URL(value.trim());
      if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password
          || url.pathname !== '/' || url.search || url.hash) throw new Error('Invalid trial origin');
      return url.origin;
    });
    return [...new Set(origins)];
  } catch { return []; }
}
function trialEnabled() {
  return process.env.ARC_TRIAL_LOGIN_ENABLED === '1' && trialOrigins().length > 0;
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
  const origin = req.headers.origin;
  return trialEnabled() && req.is('application/json') && trialOrigins().includes(origin)
    && req.headers.host === new URL(origin).host && req.headers['sec-fetch-site'] !== 'cross-site';
}

// Reserve attempts before password verification so parallel failures cannot
// bypass the limit. Use the TCP peer, never a caller's forwarding headers.
const trialAttempts = require('./loginAttemptLimiter').createLoginAttempts();

module.exports = { TRIAL_ACCOUNTS, TRIAL_SESSION_PREFIX, trialUserAllowed, trialSessionAllowed, trialLoginRequest, trialAttempts };
