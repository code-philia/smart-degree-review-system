const express = require('express');
const fs = require('fs/promises');
const path = require('path');
const { requireAuth } = require('../auth/authMiddleware');
const { createArchiveScanService } = require('./archiveScanService');
const ALLOWED_ROLES = ['COLLEGE_ADMIN', 'SCHOOL_ADMIN'];

function createArchiveScanRouter(service = createArchiveScanService()) {
  const router = express.Router();
  router.use(requireAuth({ allowedRoles: ALLOWED_ROLES }));
  const handler = (work) => async (req, res, next) => {
    try {
      await work(req, res);
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
    handler(async (req, res) => {
      const pdfPath = await service.archivePdfPath(req.params.jobId, req.params.documentId);
      const stat = await fs.stat(pdfPath);
      res.set({
        'Content-Type': 'application/pdf',
        'Cache-Control': 'private, no-store',
        'Accept-Ranges': 'bytes',
        'Content-Disposition': `inline; filename*=UTF-8''${encodeURIComponent(path.basename(pdfPath))}`,
      });
      const range = req.get('range');
      if (range) {
        const match = /^bytes=(\d*)-(\d*)$/.exec(range);
        const suffix = match && !match[1] && match[2] ? Number(match[2]) : null;
        const start = suffix !== null ? Math.max(0, stat.size - suffix) : match && match[1] ? Number(match[1]) : NaN;
        const end =
          suffix !== null
            ? stat.size - 1
            : match && match[2]
              ? Math.min(Number(match[2]), stat.size - 1)
              : stat.size - 1;
        if (!Number.isSafeInteger(start) || !Number.isSafeInteger(end) || start > end || end >= stat.size) {
          res.status(416).set('Content-Range', `bytes */${stat.size}`).end();
          return;
        }
        res
          .status(206)
          .set({ 'Content-Range': `bytes ${start}-${end}/${stat.size}`, 'Content-Length': String(end - start + 1) });
        const stream = require('fs').createReadStream(pdfPath, { start, end });
        stream.on('error', (error) => {
          if (!res.headersSent) res.status(500).end();
          else res.destroy(error);
        });
        stream.pipe(res);
        return;
      }
      res.set('Content-Length', String(stat.size));
      const stream = require('fs').createReadStream(pdfPath);
      stream.on('error', (error) => {
        if (!res.headersSent) res.status(500).end();
        else res.destroy(error);
      });
      stream.pipe(res);
    }),
  );
  return router;
}
module.exports = { createArchiveScanRouter, ALLOWED_ROLES };
