const express = require('express');
const { requireAuth } = require('../auth/authMiddleware');
const service = require('./repairSuggestionService');
const { buildArchiveRepairRequestWithPdfContext } = require('./repairEvidenceService');

const ALLOWED_ROLES = ['COLLEGE_ADMIN', 'SCHOOL_ADMIN'];

function createRepairSuggestionRouter() {
  const router = express.Router();
  router.use(requireAuth({ allowedRoles: ALLOWED_ROLES }));
  const handler = (work) => async (req, res, next) => {
    try { await work(req, res); } catch (error) {
      if (error.status) res.status(error.status).json({ code: error.status, message: error.message });
      else next(error);
    }
  };
  function archiveFindingIds(req) {
    const values = {
      jobId: req.query.job_id,
      documentId: req.query.document_id,
      ruleId: req.query.rule_id,
      findingId: req.query.finding_id,
    };
    if (!Object.values(values).every((value) => typeof value === 'string' && value.trim())) {
      throw Object.assign(new Error('需要 job_id、document_id、rule_id 和 finding_id'), { status: 400 });
    }
    return values;
  }
  router.get('/archive-findings/request', handler(async (req, res) => {
    res.json({ request: await service.buildArchiveRepairRequest(archiveFindingIds(req)) });
  }));
  router.get('/archive-findings/context', handler(async (req, res) => {
    res.json({ request: await buildArchiveRepairRequestWithPdfContext(archiveFindingIds(req)) });
  }));
  router.get('/archive-findings', handler(async (req, res) => {
    res.json({ suggestions: await service.listArchiveRepairSuggestions({
      jobId: req.query.job_id, documentId: req.query.document_id,
      ruleId: req.query.rule_id, findingId: req.query.finding_id,
    }) });
  }));
  return router;
}

module.exports = { createRepairSuggestionRouter, ALLOWED_ROLES };
