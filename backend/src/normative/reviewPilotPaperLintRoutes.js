const express = require('express');
const { requireAuth } = require('../auth/authMiddleware');
const defaultService = require('./reviewPilotPaperLintService');
const defaultExampleService = require('./paperLintExampleService');
const paperLintReportRepository = require('./paperLintReportRepository');
const { sendPrivatePdf } = require('./privatePdfResponse');
const defaultJobService = require('./paperLintJobService');
const { CLOUD_IDS } = require('./sixRulePaperLintService');

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

function createReviewPilotPaperLintRouter(service = defaultService, exampleService = defaultExampleService, jobService = defaultJobService) {
  const router = express.Router();

  router.get('/examples', requireAuth({ allowedRoles }), async (_req, res, next) => {
    try {
      res.json(await exampleService.listPaperLintExamples());
    } catch (error) {
      sendError(error, res, next);
    }
  });

  router.get('/examples/:caseId/pdf', requireAuth({ allowedRoles }), async (req, res, next) => {
    try {
      const pdf = await exampleService.readPaperLintExamplePdf(req.params.caseId);
      res.set('Content-Type', 'application/pdf');
      res.set('Content-Disposition', 'inline; filename="built-in-review-case.pdf"');
      res.send(pdf.content);
    } catch (error) {
      sendError(error, res, next);
    }
  });

  router.get('/examples/:caseId', requireAuth({ allowedRoles }), async (req, res, next) => {
    try {
      res.json(await exampleService.getPaperLintExample(req.params.caseId));
    } catch (error) {
      sendError(error, res, next);
    }
  });

  router.get('/rules', requireAuth({ allowedRoles }), async (_req, res, next) => {
    try {
      res.json(await service.getPaperLintCatalog());
    } catch (error) {
      sendError(error, res, next);
    }
  });

  router.get('/reports', requireAuth({ allowedRoles }), async (req, res, next) => {
    try {
      res.json({ records: await paperLintReportRepository.listPaperLintReportsByUser(req.user.id) });
    } catch (error) {
      sendError(error, res, next);
    }
  });

  router.get('/reports/:reportId/pdf', requireAuth({ allowedRoles }), async (req, res, next) => {
    try {
      const pdf = await paperLintReportRepository.getPaperLintReportPdfFile(req.params.reportId, req.user.id);
      if (!pdf) return res.status(404).json({ code: 404, message: '未找到该审查报告' });
      if (!pdf.path) return res.status(410).json({ code: 410, message: '该报告的原始 PDF 已不可用' });
      return sendPrivatePdf(req, res, pdf.path, pdf.source_filename, next);
    } catch (error) {
      return sendError(error, res, next);
    }
  });

  router.get('/reports/:reportId', requireAuth({ allowedRoles }), async (req, res, next) => {
    try {
      const report = await paperLintReportRepository.findPaperLintReportByIdForUser(req.params.reportId, req.user.id);
      if (!report) return res.status(404).json({ code: 404, message: '未找到该审查报告' });
      return res.json(report);
    } catch (error) {
      return sendError(error, res, next);
    }
  });

  router.get('/jobs/:jobId', requireAuth({ allowedRoles }), async (req, res, next) => {
    try {
      const job = await jobService.getForUser(req.params.jobId, req.user.id);
      if (!job) return res.status(404).json({ code: 404, message: '未找到该检查任务' });
      return res.json(job);
    } catch (error) {
      return sendError(error, res, next);
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
        const externalProcessingConsent = req.get('x-paper-lint-external-processing-consent') === 'confirmed';
        if (selectedRuleIds.some((id) => CLOUD_IDS.has(id))) {
          service.validatePdf(req.body);
          const normalizedRuleIds = await service.normalizeSelectedRuleIds(selectedRuleIds, externalProcessingConsent);
          const job = await jobService.enqueue({
            userId: req.user.id,
            sourceFilename: typeof req.query.filename === 'string' ? req.query.filename.slice(0, 255) : '论文.pdf',
            pdfBuffer: req.body, selectedRuleIds: normalizedRuleIds, externalProcessingConsent,
          });
          return res.status(202).json(job);
        }        const { result, selectedRuleIds: normalizedRuleIds } = await service.runPaperLint({
          pdfBuffer: req.body,
          selectedRuleIds,
          externalProcessingConsent,
        });
        const report = await paperLintReportRepository.createPaperLintReport({
          userId: req.user.id,
          sourceFilename: typeof req.query.filename === 'string' ? req.query.filename.slice(0, 255) : '论文.pdf',
          pdfBuffer: req.body,
          selectedRuleIds: normalizedRuleIds,
          result,
        });
        res.status(201).json(report);
      } catch (error) {
        sendError(error, res, next);
      }
    },
  );

  return router;
}

module.exports = createReviewPilotPaperLintRouter();
module.exports.createReviewPilotPaperLintRouter = createReviewPilotPaperLintRouter;
