const ADMIN_ROLES = Object.freeze(['SCHOOL_ADMIN', 'COLLEGE_ADMIN']);
const LOOPBACK_ADDRESSES = new Set(['127.0.0.1', '::1', '::ffff:127.0.0.1']);
const LOOPBACK_HOSTS = new Set(['127.0.0.1', 'localhost', '[::1]']);

function campusOnlyAuth() {
  return process.env.NODE_ENV === 'production' || process.env.ARC_AUTH_MODE === 'jaccount-only';
}

function adminPort() {
  const port = Number(process.env.ARC_ADMIN_PORT || 3002);
  if (!Number.isInteger(port) || port < 1 || port > 65535 || port === Number(process.env.PORT || 3000)) {
    throw new Error('ARC_ADMIN_PORT must be a valid port separate from the public listener');
  }
  return port;
}

function loopbackAuthority(host) {
  if (typeof host !== 'string') return null;
  try {
    const url = new URL('http://' + host);
    if (!LOOPBACK_HOSTS.has(url.hostname) || url.username || url.password || url.pathname !== '/' || url.search || url.hash) return null;
    return url.host;
  } catch { return null; }
}

function privateAdminRequest(req) {
  // Only the actual loopback TCP listener grants access. Forwarded headers and
  // Express trust-proxy settings cannot turn a public connection into this one.
  if (!LOOPBACK_ADDRESSES.has(req.socket?.remoteAddress) || req.socket?.localPort !== adminPort()) return false;
  const authority = loopbackAuthority(req.headers.host);
  if (!authority) return false;
  if (req.headers.origin) {
    try {
      const origin = new URL(req.headers.origin);
      if (!['http:', 'https:'].includes(origin.protocol) || origin.host !== authority) return false;
    } catch { return false; }
  }
  return true;
}

function campusUserAllowed(user) {
  return Boolean(user) && !ADMIN_ROLES.includes(user.role);
}

function sessionAllowed(req, user) {
  if (!user) return false;
  if (!campusOnlyAuth()) return true;
  if (privateAdminRequest(req)) return ADMIN_ROLES.includes(user.role);
  return typeof user.id === 'string' && user.id.startsWith('jaccount:') && campusUserAllowed(user);
}

module.exports = { ADMIN_ROLES, campusOnlyAuth, adminPort, privateAdminRequest, campusUserAllowed, sessionAllowed };
