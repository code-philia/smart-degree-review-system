const express = require('express');
const { SESSION_COOKIE_NAME, SESSION_TTL_MS, loadSession, login, logout } = require('./sessionService');
const { parseCookies, requireAuth } = require('./authMiddleware');
const jaccount = require('./jaccountService');

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

router.get('/jaccount/config', (req, res) => {
  res.json({ enabled: jaccount.isConfigured() });
});

router.get('/jaccount', async (req, res) => {
  res.set('Cache-Control', 'no-store');
  try {
    const result = await jaccount.beginLogin();
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
    res.redirect('/thirty-rules-check');
  } catch (error) {
    res.redirect(`/auth?jaccount_error=${error.jaccountCode || 'provider'}`);
  }
});

router.post('/login', async (req, res, next) => {
  try {
    const result = await login(req.body?.username, req.body?.password);
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
    if (!user) {
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
