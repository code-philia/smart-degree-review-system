const crypto = require('crypto');
const bcrypt = require('bcrypt');
const sessionRepository = require('./sessionRepository');
const { TRIAL_SESSION_PREFIX, trialUserAllowed } = require('./trialLoginPolicy');

const SESSION_COOKIE_NAME = 'arc_session';
const SESSION_TTL_MS = 1000 * 60 * 60 * 8;

function serializeUser(row) {
  if (!row) {
    return null;
  }

  return {
    id: row.userId || row.id,
    username: row.username,
    ...(row.displayName ? { displayName: row.displayName } : {}),
    ...(row.email ? { email: row.email } : {}),
    ...(['zh', 'en'].includes(row.defaultLocale) ? { defaultLocale: row.defaultLocale } : {}),
    role: row.role,
    collegeId: row.collegeId || null,
    supervisorId: row.supervisorId || null,
    scope: row.scope,
  };
}

async function login(username, password, { allowedRoles, allowedUser, sessionKind } = {}) {
  if (typeof username !== 'string' || typeof password !== 'string' || !username || !password) return null;
  const user = await sessionRepository.findUserByUsername(username);
  if (!user || (allowedRoles && !allowedRoles.includes(user.role)) || (allowedUser && !allowedUser(user))) {
    return null;
  }

  const passwordMatches = await bcrypt.compare(password, user.passwordHash);
  if (!passwordMatches) {
    return null;
  }

  return createUserSession(user, { kind: sessionKind });
}

async function createUserSession(user, { kind } = {}) {
  if (kind === 'trial' && !trialUserAllowed(user)) throw new Error('Invalid trial identity');
  const sessionId = (kind === 'trial' ? TRIAL_SESSION_PREFIX : '') + crypto.randomUUID();
  const expiresAt = new Date(Date.now() + SESSION_TTL_MS).toISOString();
  await sessionRepository.createSession(sessionId, user.id, expiresAt);

  return {
    sessionId,
    user: serializeUser(user),
  };
}

async function loadSession(sessionId) {
  if (!sessionId) {
    return null;
  }

  const session = await sessionRepository.findSession(sessionId);
  if (!session || new Date(session.expiresAt).getTime() <= Date.now()) {
    if (session) {
      await sessionRepository.deleteSession(sessionId);
    }
    return null;
  }

  return serializeUser(session);
}

async function logout(sessionId) {
  if (sessionId) {
    await sessionRepository.deleteSession(sessionId);
  }
}

module.exports = {
  SESSION_COOKIE_NAME,
  SESSION_TTL_MS,
  createUserSession,
  login,
  loadSession,
  logout,
};
