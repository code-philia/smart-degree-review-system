const express = require('express');
const { requireAuth } = require('../auth/authMiddleware');
const {
  ALLOWED_REPORT_SUPERVISOR_QUEUE_ROLES,
  getSupervisorReviewQueueBadge,
  listSupervisorReviewQueue,
} = require('./reportSupervisorQueueService');
const {
  ALLOWED_REPORT_SUPERVISOR_REVIEW_ROLES,
  getSupervisorReviewDetail,
  submitSupervisorReview,
} = require('./reportSupervisorReviewService');

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

router.get(
  '/:submissionId',
  requireAuth({ allowedRoles: ALLOWED_REPORT_SUPERVISOR_REVIEW_ROLES }),
  async (req, res, next) => {
    try {
      const result = await getSupervisorReviewDetail(req.user, req.params.submissionId);
      res.json(result);
    } catch (error) {
      sendSupervisorQueueError(error, res, next);
    }
  },
);

router.post(
  '/:submissionId/review',
  requireAuth({ allowedRoles: ALLOWED_REPORT_SUPERVISOR_REVIEW_ROLES }),
  express.json({ limit: '128kb' }),
  async (req, res, next) => {
    try {
      const result = await submitSupervisorReview(req.user, req.params.submissionId, req.body || {});
      res.status(201).json(result);
    } catch (error) {
      sendSupervisorQueueError(error, res, next);
    }
  },
);

module.exports = router;
