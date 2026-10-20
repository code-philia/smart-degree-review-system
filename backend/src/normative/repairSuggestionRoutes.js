const { shareRepairGeneration } = require('./repairGenerationFlight');
const express = require('express');
const { requireAuth } = require('../auth/authMiddleware');
const service = require('./repairSuggestionService');
const { buildArchiveRepairRequestWithPdfContext } = require('./repairEvidenceService');
const { PROMPT_VERSION, proposeRepair, getRepairModelIdentity } = require('./repairModelProposalService');

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
  router.post('/archive-findings/evaluate', express.json({ limit: '16kb' }), handler(async (req, res) => {
    const values = {
      jobId: req.body?.job_id, documentId: req.body?.document_id,
      ruleId: req.body?.rule_id, findingId: req.body?.finding_id,
    };
    if (!Object.values(values).every((value) => typeof value === 'string' && value.trim())) {
      res.status(400).json({ code: 400, message: '需要 job_id、document_id、rule_id 和 finding_id' });
      return;
    }
    const request = await buildArchiveRepairRequestWithPdfContext(values);
    const { model, modelVersion } = await getRepairModelIdentity();
    const force = req.body?.force === true;
    const result = await shareRepairGeneration(JSON.stringify(['archive', request.context_sha256, model, modelVersion, PROMPT_VERSION, force]), async () => {
      const cached = !force && model ? await service.findRepairSuggestion(request, {model, modelVersion, promptVersion: PROMPT_VERSION}) : null;
      if (cached) return {response: cached, cached: true};
      const response = await proposeRepair(request);
      await service.saveRepairSuggestion(request, response);
      return {response, cached: false};
    });
    res.status(result.cached ? 200 : 201).json(result);
  }));
  router.get('/archive-findings', handler(async (req, res) => {
    const values = archiveFindingIds(req);
    const request = await service.buildArchiveRepairRequest(values);
    const identity = await getRepairModelIdentity();
    const suggestions = await service.listArchiveRepairSuggestions(values);
    res.json({ suggestions: suggestions.filter(({ response }) =>
      response.provenance.model === identity.model && response.provenance.model_version === identity.modelVersion &&
      response.provenance.prompt_version === PROMPT_VERSION &&
      response.provenance.source_identity_sha256 === request.source_identity_sha256) });
  }));
  return router;
}

module.exports = { createRepairSuggestionRouter, ALLOWED_ROLES };
