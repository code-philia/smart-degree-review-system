const express = require('express');
const path = require('path');
const { requireAuth } = require('../auth/authMiddleware');
const { createArchiveScanService } = require('./archiveScanService');
const { sendPrivatePdf } = require('./privatePdfResponse');
const ALLOWED_ROLES = ['COLLEGE_ADMIN', 'SCHOOL_ADMIN'];

function createArchiveScanRouter(service = createArchiveScanService()) {
  const router = express.Router();
  router.use(requireAuth({ allowedRoles: ALLOWED_ROLES }));
  const handler = (work) => async (req, res, next) => {
    try {
      await work(req, res, next);
    } catch (error) {
      if (error.status) res.status(error.status).json({ code: error.status, message: error.message });
      else next(error);
    }
  };
  router.get(
    '/',
    handler(async (_req, res) => {
      const documents = await service.listArchivePdfs();
      res.json({ rules: service.rules, paper_count: documents.length });
    }),
  );
  router.get(
    '/jobs',
    handler(async (_req, res) => res.json({ jobs: await service.listJobs() })),
  );
  router.post(
    '/jobs',
    express.json({ limit: '16kb' }),
    handler(async (req, res) => {
      const job = await service.startJob({ userId: req.user.id, ruleIds: req.body?.selected_rule_ids });
      res.status(201).json({ job });
    }),
  );
  router.get(
    '/jobs/:jobId',
    handler(async (req, res) => res.json({ job: await service.getJob(req.params.jobId) })),
  );
  router.delete(
    '/jobs/:jobId',
    handler(async (req, res) => {
      await service.deleteJob(req.params.jobId);
      res.status(204).end();
    }),
  );
  router.get(
    '/jobs/:jobId/documents',
    handler(async (req, res) => {
      res.json(
        await service.listDocuments(req.params.jobId, {
          ruleId: req.query.rule_id,
          outcome: req.query.outcome,
          query: req.query.q,
          page: req.query.page,
        }),
      );
    }),
  );
  router.get(
    '/jobs/:jobId/documents/:documentId',
    handler(async (req, res) => {
      res.json({ document: await service.getDocument(req.params.jobId, req.params.documentId) });
    }),
  );
  router.get(
    '/jobs/:jobId/documents/:documentId/pdf',
    handler(async (req, res, next) => {
      const pdfPath = await service.archivePdfPath(req.params.jobId, req.params.documentId);
      sendPrivatePdf(req, res, pdfPath, path.basename(pdfPath), next);
    }),
  );
  return router;
}
module.exports = { createArchiveScanRouter, ALLOWED_ROLES };
