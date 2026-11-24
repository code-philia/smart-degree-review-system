const express = require('express');
const { requireAuth } = require('./authMiddleware');
const { campusOnlyAuth, privateAdminRequest } = require('./loginPolicy');
const settings = require('./referenceSettingsService');

const router = express.Router();

function configuredOrigin(value, allowPath = false) {
  if (typeof value !== 'string' || !value.trim()) return null;
  try {
    const url = new URL(value.trim());
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password
      || url.search || url.hash || (!allowPath && url.pathname !== '/')) return null;
    return url.origin;
  } catch {
    return null;
  }
}

function trustedOrigins() {
  const values = [configuredOrigin(process.env.APP_PUBLIC_URL), configuredOrigin(process.env.JACCOUNT_REDIRECT_URI, true)];
  values.push(...String(process.env.ARC_CORS_ORIGIN || '').split(',').map(value => configuredOrigin(value)));
  if (process.env.ARC_TRIAL_LOGIN_ENABLED === '1') {
    const trials = process.env.ARC_TRIAL_LOGIN_ORIGINS === undefined
      ? process.env.ARC_TRIAL_LOGIN_ORIGIN || '' : process.env.ARC_TRIAL_LOGIN_ORIGINS;
    values.push(...trials.split(',').map(value => configuredOrigin(value)));
  }
  return values.filter(Boolean);
}

function sameOriginWrite(req) {
  const origin = configuredOrigin(req.headers.origin);
  if (!origin || req.headers.origin !== origin || new URL(origin).host !== req.headers.host
    || req.headers['sec-fetch-site'] === 'cross-site') return false;
  if (trustedOrigins().includes(origin)) return true;
  // Local admin access is authorized by the actual TCP listener, never a
  // caller-controlled Forwarded header. Development is local-only as well.
  if (privateAdminRequest(req)) return true;
  return !campusOnlyAuth() && origin.startsWith('http://')
    && ['localhost', '127.0.0.1', '[::1]'].includes(new URL(origin).hostname)
    && ['127.0.0.1', '::1', '::ffff:127.0.0.1'].includes(req.socket?.remoteAddress);
}

function secureTransportRequired(req) {
  if (!campusOnlyAuth() || privateAdminRequest(req)) return false;
  const origins = trustedOrigins();
  const origin = configuredOrigin(req.headers.origin);
  const allowDevelopmentHttp = process.env.REFERENCE_SETTINGS_ALLOW_INSECURE_DEVELOPMENT === '1';
  if (req.headers.origin) {
    const trusted = origin && origin === req.headers.origin && origins.includes(origin)
      && new URL(origin).host === req.headers.host;
    return !trusted || (new URL(origin).protocol !== 'https:' && !allowDevelopmentHttp);
  }
  // The canonical deployment config describes TLS termination when a same-origin
  // GET has no Origin header. Forwarded headers never grant the exception.
  if (req.socket?.encrypted) return false;
  return !origins.some(value => new URL(value).host === req.headers.host
    && (new URL(value).protocol === 'https:' || allowDevelopmentHttp));
}

function publicResponse(req, value) {
  return secureTransportRequired(req) ? { ...value, storage_available: false, secure_transport_required: true } : value;
}

function reject(res, status, errorCode) {
  return res.status(status).json({ code: status, error_code: errorCode, message: 'Reference settings request failed' });
}

router.use((req, res, next) => {
  res.set('Cache-Control', 'private, no-store');
  next();
});
router.use(requireAuth());
router.use((req, res, next) => {
  if (['PUT', 'DELETE'].includes(req.method)) {
    if (!sameOriginWrite(req)) return reject(res, 403, 'origin_not_allowed');
    if (req.method === 'PUT' && secureTransportRequired(req)) return reject(res, 403, 'secure_transport_required');
    if (!req.is('application/json')) return reject(res, 415, 'json_required');
  }
  return next();
});
router.use(express.json({ limit: '2kb' }));

router.get('/', async (req, res) => {
  try {
    return res.json(publicResponse(req, await settings.getReferenceSettings(req.user.id)));
  } catch {
    return reject(res, 503, 'storage_unavailable');
  }
});

for (const method of ['put', 'delete']) {
  router[method]('/', async (req, res) => {
    // This is a precondition only. The session's ID is always the storage key.
    if (req.body?.expected_user_id !== req.user.id) return reject(res, 409, 'account_changed');
    try {
      const result = method === 'put'
        ? await settings.saveReferenceSettings(req.user.id, req.body)
        : await settings.deleteReferenceSettings(req.user.id, req.body?.provider);
      return res.json(publicResponse(req, result));
    } catch (error) {
      if (['invalid_api_key', 'invalid_serpapi_key', 'invalid_provider'].includes(error.errorCode)) return reject(res, 400, error.errorCode);
      return reject(res, 503, 'storage_unavailable');
    }
  });
}

// Parser and authentication failures must never reach Express's default error
// page/logger: a malformed JSON error can contain the submitted secret.
router.use((error, req, res, next) => {
  if (error?.type === 'entity.too.large') return reject(res, 413, 'request_too_large');
  if (error?.type === 'entity.parse.failed') return reject(res, 400, 'invalid_json');
  return reject(res, 503, 'storage_unavailable');
});

module.exports = router;
