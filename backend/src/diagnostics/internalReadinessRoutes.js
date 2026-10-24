const express = require('express');
const { buildReadinessSnapshot } = require('./internalReadinessService');

const router = express.Router();

function authorized(req) {
  const token = process.env.ARC_READINESS_TOKEN;
  return Boolean(token && req.get('x-readiness-token') === token);
}

router.get('/readiness', async (req, res, next) => {
  if (!authorized(req)) return res.status(404).json({ code: 404, message: 'Not found' });
  try {
    const snapshot = await buildReadinessSnapshot();
    return res.status(snapshot.ok ? 200 : 503).json(snapshot);
  } catch (error) {
    return next(error);
  }
});

module.exports = router;
