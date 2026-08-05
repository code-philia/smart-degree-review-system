const express = require('express');
const { requireAuth } = require('../auth/authMiddleware');
const {
  ALLOWED_REPORT_SUPERVISOR_QUEUE_ROLES,
  getSupervisorReviewQueueBadge,
  listSupervisorReviewQueue,
} = require('./reportSupervisorQueueService');

const router = express.Router();

function sendSupervisorQueueError(error, res, next) {
  if (error?.status) {
    res.status(error.status).json({ code: error.status, message: error.message });
    return;
  }
  next(error);
}

router.get(
  '/',
  requireAuth({ allowedRoles: ALLOWED_REPORT_SUPERVISOR_QUEUE_ROLES }),
  async (req, res, next) => {
    try {
      const result = await listSupervisorReviewQueue(req.user, req.query || {});
      res.json(result);
    } catch (error) {
      sendSupervisorQueueError(error, res, next);
    }
  },
);

router.get(
  '/badge',
  requireAuth({ allowedRoles: ALLOWED_REPORT_SUPERVISOR_QUEUE_ROLES }),
  async (req, res, next) => {
    try {
      const result = await getSupervisorReviewQueueBadge(req.user);
      res.json(result);
    } catch (error) {
      sendSupervisorQueueError(error, res, next);
    }
  },
);

module.exports = router;
