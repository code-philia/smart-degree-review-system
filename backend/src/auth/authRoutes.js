const express = require('express');
const { SESSION_COOKIE_NAME, SESSION_TTL_MS, loadSession, login, logout } = require('./sessionService');
const { parseCookies, requireAuth } = require('./authMiddleware');

const router = express.Router();

const cookieOptions = {
  httpOnly: true,
  sameSite: 'lax',
  // The site currently terminates on HTTP. Enable this explicitly when the
  // public endpoint is HTTPS; NODE_ENV alone does not describe that boundary.
  secure: process.env.ARC_COOKIE_SECURE === '1',
  path: '/',
};

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
