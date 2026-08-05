const express = require('express');
const { requireAuth } = require('../auth/authMiddleware');
const {
  ALLOWED_REPORT_SUBMISSION_ROLES,
  createReportSubmissionsForStudent,
} = require('./reportSubmissionService');

const router = express.Router();

function sendReportSubmissionError(error, res, next) {
  if (error?.status) {
    res.status(error.status).json({ code: error.status, message: error.message });
    return;
  }
  next(error);
}

router.post(
  '/',
  requireAuth({ allowedRoles: ALLOWED_REPORT_SUBMISSION_ROLES }),
  express.json({ limit: '128kb' }),
  async (req, res, next) => {
    try {
      const result = await createReportSubmissionsForStudent(req.user, req.body || {});
      res.status(201).json(result);
    } catch (error) {
      sendReportSubmissionError(error, res, next);
    }
  },
);

module.exports = router;
