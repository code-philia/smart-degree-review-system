const express = require('express');
const { requireAuth } = require('../auth/authMiddleware');
const {
  ALLOWED_REPORT_STUDENT_RESULTS_ROLES,
  buildStudentReportResultDownloadPayload,
  getStudentReportResultDetail,
  listStudentReportResults,
} = require('./reportStudentResultsService');

const router = express.Router();

function sendStudentResultsError(error, res, next) {
  if (error?.status) {
    res.status(error.status).json({ code: error.status, message: error.message });
    return;
  }
  next(error);
}

router.get(
  '/',
  requireAuth({ allowedRoles: ALLOWED_REPORT_STUDENT_RESULTS_ROLES }),
  async (req, res, next) => {
    try {
      const result = await listStudentReportResults(req.user, req.query || {});
      res.json(result);
    } catch (error) {
      sendStudentResultsError(error, res, next);
    }
  },
);

router.get(
  '/:submissionId',
  requireAuth({ allowedRoles: ALLOWED_REPORT_STUDENT_RESULTS_ROLES }),
  async (req, res, next) => {
    try {
      const result = await getStudentReportResultDetail(req.user, req.params.submissionId);
      res.json(result);
    } catch (error) {
      sendStudentResultsError(error, res, next);
    }
  },
);

router.get(
  '/:submissionId/download',
  requireAuth({ allowedRoles: ALLOWED_REPORT_STUDENT_RESULTS_ROLES }),
  async (req, res, next) => {
    try {
      const payload = await buildStudentReportResultDownloadPayload(req.user, req.params.submissionId);
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.setHeader('Content-Disposition', `attachment; filename="student-report-result-${req.params.submissionId}.json"`);
      res.json(payload);
    } catch (error) {
      sendStudentResultsError(error, res, next);
    }
  },
);

module.exports = router;
