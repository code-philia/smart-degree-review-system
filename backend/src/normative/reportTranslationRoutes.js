const express = require('express');
const { requireAuth } = require('../auth/authMiddleware');
const { createTranslationService } = require('./reportTranslationService');

function createReportTranslationRouter({ translate = createTranslationService() } = {}) {
  const router = express.Router();
  router.use(requireAuth({ allowedRoles: ['STUDENT', 'SUPERVISOR', 'SCHOOL_ADMIN', 'COLLEGE_ADMIN'] }));
  const handler = async (req, res, next) => {
    try {
      if (!req.body || Array.isArray(req.body) || req.body.locale !== 'en' ||
          Object.keys(req.body).length !== 1) {
        res.status(400).json({ code: 400, message: 'Expected only locale: en' }); return;
      }
      const response = await translate({
        userId: req.user.id, reportId: req.params.reportId, jobId: req.params.jobId, locale: req.body.locale,
      });
      res.set('Cache-Control', 'no-store').json(response);
    } catch (error) {
      if (error.status) res.status(error.status).json({ code: error.status, message: error.message });
      else next(error);
    }
  };
  router.post('/reports/:reportId/translations', express.json({ limit: '1kb' }), handler);
  router.post('/jobs/:jobId/translations', express.json({ limit: '1kb' }), handler);
  return router;
}
module.exports = { createReportTranslationRouter };
