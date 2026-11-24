const SUPERVISION_SESSION_PREFIX = 'supervision:';

function isSupervisionAccount(user) {
  return Boolean(user) && user.id === 'admin' && user.username === 'admin'
    && user.role === 'SCHOOL_ADMIN' && user.scope === 'SCHOOL';
}

function supervisionSessionAllowed(user, sessionId) {
  return isSupervisionAccount(user) && typeof sessionId === 'string'
    && sessionId.startsWith(SUPERVISION_SESSION_PREFIX);
}

function supervisionLoginRequest(req) {
  try {
    const url = new URL(process.env.APP_PUBLIC_URL || '');
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password
        || url.pathname !== '/' || url.search || url.hash) return false;
    return req.is('application/json') && req.headers.origin === url.origin
      && req.headers.host === url.host && req.headers['sec-fetch-site'] !== 'cross-site';
  } catch { return false; }
}

const supervisionAttempts = require('./loginAttemptLimiter').createLoginAttempts();
module.exports = { SUPERVISION_SESSION_PREFIX, isSupervisionAccount, supervisionSessionAllowed, supervisionLoginRequest, supervisionAttempts };
