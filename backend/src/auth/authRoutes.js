const express = require('express');
const { SESSION_COOKIE_NAME, SESSION_TTL_MS, loadSession, login, logout } = require('./sessionService');
const { parseCookies, requireAuth } = require('./authMiddleware');
const jaccount = require('./jaccountService');
const { ADMIN_ROLES, campusOnlyAuth, privateAdminRequest, sessionAllowed } = require('./loginPolicy');
const { trialUserAllowed, trialLoginRequest, trialAttempts } = require('./trialLoginPolicy');
const { normalizeEmail, notificationEmail, fixedNotificationEmail, campusIdentity } = require('../notifications/emailPolicy');
const { mailConfig } = require('../notifications/mailConfig');
const { run } = require('../database');

const router = express.Router();

const cookieOptions = {
  httpOnly: true,
  sameSite: 'lax',
  // The site currently terminates on HTTP. Enable this explicitly when the
  // public endpoint is HTTPS; NODE_ENV alone does not describe that boundary.
  secure: process.env.ARC_COOKIE_SECURE === '1',
  path: '/',
};

const campusCookieOptions = { ...cookieOptions, path: '/api/auth/jaccount' };

function notificationSettings(user) {
  return { email: notificationEmail(user), fixed: fixedNotificationEmail(user)||campusIdentity(user), delivery_available: Boolean(mailConfig()) };
}
router.get('/notification-settings', requireAuth(), (req, res) => {
  res.set('Cache-Control', 'private, no-store');
  res.json(notificationSettings(req.user));
});
router.put('/notification-settings', requireAuth(), express.json({ limit: '2kb' }), async (req, res, next) => {
  if (fixedNotificationEmail(req.user)||campusIdentity(req.user)) return res.status(403).json({ code:403, message:'此账号的通知邮箱由系统确认，无需修改。' });
  const email = normalizeEmail(req.body?.email);
  if (!email) return res.status(400).json({ code:400, message:'请输入一个有效的接收邮箱。' });
  try {
    await run('UPDATE auth_users SET email=? WHERE id=?',[email,req.user.id]);
    await run("UPDATE report_email_outbox SET status='pending', next_attempt_at=?, error_code=NULL WHERE user_id=? AND status='blocked' AND error_code='missing_recipient'",[new Date().toISOString(),req.user.id]);
    return res.json(notificationSettings({ ...req.user,email }));
  } catch (error) { return next(error); }
});

router.post('/trial-login', async (req, res, next) => {
  res.set('Cache-Control', 'no-store');
  try {
    if (!trialLoginRequest(req)) {
      res.status(403).json({ code: 403, message: '试验账号登录暂不可用，请联系管理员。' });
      return;
    }
    const retryAfter = trialAttempts.consume(req);
    if (retryAfter) {
      res.set('Retry-After', String(retryAfter));
      res.status(429).json({ code: 429, message: '尝试次数过多，请稍后再试。' });
      return;
    }
    const username = req.body?.username;
    const password = req.body?.password;
    const result = typeof username === 'string' && username.length <= 128
      && typeof password === 'string' && password.length <= 256
      ? await login(username, password, { allowedUser: trialUserAllowed, sessionKind: 'trial' }) : null;
    if (!result) {
      res.status(401).json({ code: 401, message: '账号或密码错误，请重试。' });
      return;
    }
    res.cookie(SESSION_COOKIE_NAME, result.sessionId, { ...cookieOptions, maxAge: SESSION_TTL_MS });
    res.json({ user: result.user });
  } catch (error) { next(error); }
});

router.get('/jaccount/config', (req, res) => {
  res.json({ enabled: jaccount.isConfigured() });
});

router.get('/jaccount', async (req, res) => {
  res.set('Cache-Control', 'no-store');
  try {
    const result = await jaccount.beginLogin(req.query.return_to);
    res.cookie(jaccount.STATE_COOKIE_NAME, result.state, { ...campusCookieOptions, maxAge: jaccount.STATE_TTL_MS });
    res.redirect(result.url);
  } catch (error) {
    res.redirect(`/auth?jaccount_error=${error.jaccountCode || 'unavailable'}`);
  }
});

router.get('/jaccount/callback', async (req, res) => {
  res.set('Cache-Control', 'no-store');
  const cookies = parseCookies(req.headers.cookie || '');
  res.clearCookie(jaccount.STATE_COOKIE_NAME, campusCookieOptions);
  try {
    const result = await jaccount.completeLogin({ state: req.query.state,
      browserState: cookies[jaccount.STATE_COOKIE_NAME], code: req.query.code, providerError: req.query.error });
    res.cookie(SESSION_COOKIE_NAME, result.sessionId, { ...cookieOptions, maxAge: SESSION_TTL_MS });
    res.redirect(result.returnTo || '/paper-upload');
  } catch (error) {
    res.redirect(`/auth?jaccount_error=${error.jaccountCode || 'provider'}`);
  }
});

router.post('/login', async (req, res, next) => {
  try {
    if (campusOnlyAuth() && !privateAdminRequest(req)) {
      res.status(403).json({ code: 403, message: '请使用 jAccount 登录' });
      return;
    }
    const result = await login(req.body?.username, req.body?.password,
      { allowedRoles: campusOnlyAuth() ? ADMIN_ROLES : undefined });
    if (!result) {
      res.status(401).json({ code: 401, message: 'Invalid username or password' });
      return;
    }

    res.cookie(SESSION_COOKIE_NAME, result.sessionId, {
      ...cookieOptions,
      maxAge: SESSION_TTL_MS,
    });
    res.json({ user: result.user });
  } catch (error) {
    next(error);
  }
});

router.get('/me', async (req, res, next) => {
  try {
    const cookies = parseCookies(req.headers.cookie || '');
    const user = await loadSession(cookies[SESSION_COOKIE_NAME]);
    if (!sessionAllowed(req, user, cookies[SESSION_COOKIE_NAME])) {
      res.status(401).json({ code: 401, message: 'Authentication required' });
      return;
    }
    res.json({ user });
  } catch (error) {
    next(error);
  }
});

router.post('/logout', requireAuth(), async (req, res, next) => {
  try {
    const cookies = parseCookies(req.headers.cookie || '');
    await logout(cookies[SESSION_COOKIE_NAME]);
    res.clearCookie(SESSION_COOKIE_NAME, cookieOptions);
    res.status(204).send();
  } catch (error) {
    next(error);
  }
});

module.exports = router;
