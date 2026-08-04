const { SESSION_COOKIE_NAME, loadSession } = require('./sessionService');

function parseCookies(cookieHeader = '') {
  return cookieHeader.split(';').reduce((cookies, pair) => {
    const [rawName, ...rawValue] = pair.trim().split('=');
    if (!rawName) {
      return cookies;
    }
    cookies[rawName] = decodeURIComponent(rawValue.join('='));
    return cookies;
  }, {});
}

function isRoleAllowed(user, allowedRoles) {
  return !allowedRoles || allowedRoles.length === 0 || allowedRoles.includes(user.role);
}

function hasDataScope(user, scope) {
  if (!scope || user.scope === 'SCHOOL') {
    return true;
  }
  if (scope.collegeId) {
    return user.collegeId === scope.collegeId;
  }
  if (scope.supervisorId) {
    return user.supervisorId === scope.supervisorId || user.id === scope.supervisorId;
  }
  return true;
}

function requireAuth(options = {}) {
  return async (req, res, next) => {
    const cookies = parseCookies(req.headers.cookie || '');
    const user = await loadSession(cookies[SESSION_COOKIE_NAME]);

    if (!user) {
      res.status(401).json({ code: 401, message: 'Authentication required' });
      return;
    }

    if (!isRoleAllowed(user, options.allowedRoles) || !hasDataScope(user, options.scope)) {
      res.status(403).json({ code: 403, message: 'Forbidden' });
      return;
    }

    req.user = user;
    next();
  };
}

module.exports = {
  parseCookies,
  requireAuth,
};
