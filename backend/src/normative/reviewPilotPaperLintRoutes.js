const express = require('express');
const { requireAuth } = require('../auth/authMiddleware');
const defaultService = require('./reviewPilotPaperLintService');

const allowedRoles = ['STUDENT', 'SUPERVISOR', 'SCHOOL_ADMIN', 'COLLEGE_ADMIN'];

function sendError(error, res, next) {
  if (error?.type === 'entity.too.large') {
    res.status(413).json({ code: 413, message: 'PDF 文件大小不能超过 50 MB' });
  } else if (error?.status) {
    res.status(error.status).json({ code: error.status, message: error.message });
  } else {
    next(error);
  }
}

function createReviewPilotPaperLintRouter(service = defaultService) {
  const router = express.Router();

  router.get('/rules', requireAuth({ allowedRoles }), async (_req, res, next) => {
    try {
      res.json(await service.getPaperLintCatalog());
    } catch (error) {
      sendError(error, res, next);
    }
  });

  router.post(
    '/run',
    requireAuth({ allowedRoles }),
    express.raw({ type: 'application/pdf', limit: service.MAX_PDF_BYTES }),
    async (req, res, next) => {
      try {
        const selectedRuleIds = String(req.get('x-paper-lint-rule-ids') || '')
          .split(',')
          .map((value) => value.trim())
          .filter(Boolean);
        const { result, selectedRuleIds: normalizedRuleIds } = await service.runPaperLint({
          pdfBuffer: req.body,
          selectedRuleIds,
        });
        res.json({
          source_filename: typeof req.query.filename === 'string' ? req.query.filename.slice(0, 255) : '论文.pdf',
          selected_rule_ids: normalizedRuleIds,
          processed_at: new Date().toISOString(),
          result,
        });
      } catch (error) {
        sendError(error, res, next);
      }
    },
  );

  return router;
}

module.exports = createReviewPilotPaperLintRouter();
module.exports.createReviewPilotPaperLintRouter = createReviewPilotPaperLintRouter;
