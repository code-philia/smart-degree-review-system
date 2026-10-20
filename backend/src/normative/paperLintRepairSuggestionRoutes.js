const { shareRepairGeneration } = require('./repairGenerationFlight');
const express = require('express');
const { requireAuth } = require('../auth/authMiddleware');
const service = require('./paperLintRepairSuggestionService');
const { PROMPT_VERSION, proposeRepair, getRepairModelIdentity } = require('./repairModelProposalService');

const ALLOWED_ROLES = ['STUDENT', 'SUPERVISOR', 'SCHOOL_ADMIN', 'COLLEGE_ADMIN'];

function problem(status, message) {
  const error = new Error(message);
  error.status = status;
  return error;
}

function findingIds(input) {
  const values = { ruleId: input.rule_id, findingId: input.finding_id };
  if (!Object.values(values).every((value) => typeof value === 'string' && value.trim())) {
    throw problem(400, '需要 rule_id 和 finding_id');
  }
  return values;
}

function createPaperLintRepairSuggestionRouter({ modelIdentity = getRepairModelIdentity } = {}) {
  const router = express.Router();
  router.use(requireAuth({ allowedRoles: ALLOWED_ROLES }));
  const handler = (work) => async (req, res, next) => {
    try { await work(req, res); } catch (error) {
      if (error.status) res.status(error.status).json({ code: error.status, message: error.message });
      else next(error);
    }
  };

  router.get('/reports/:reportId/repair-suggestions', handler(async (req, res) => {
    const { ruleId, findingId } = findingIds(req.query);
    await service.getPaperLintReportFinding({
      reportId: req.params.reportId, userId: req.user.id, ruleId, findingId,
    });
    const { request } = await service.buildPaperLintReportRepairRequestBase({
      reportId: req.params.reportId, userId: req.user.id, ruleId, findingId,
    });
    const response = await service.findLatestPaperLintRepairSuggestion({
      reportId: req.params.reportId, userId: req.user.id, ruleId, findingId,
      identity: { ...await modelIdentity(), promptVersion: PROMPT_VERSION },
      sourceIdentity: request.source_identity_sha256,
    });
    res.json({ response, cached: Boolean(response) });
  }));

  router.post('/reports/:reportId/repair-suggestions', express.json({ limit: '4kb' }), handler(async (req, res) => {
    const { ruleId, findingId } = findingIds(req.body || {});
    const force = req.body?.force === true;
    const request = await service.buildPaperLintReportRepairRequestWithPdfContext({
      reportId: req.params.reportId, userId: req.user.id, ruleId, findingId,
    });
    const { model, modelVersion } = await modelIdentity();
    const result = await shareRepairGeneration(JSON.stringify(['report', req.user.id, request.context_sha256, model, modelVersion, PROMPT_VERSION, force]), async () => {
      const cached = !force && model ? await service.findPaperLintRepairSuggestion(request, {model, modelVersion, promptVersion: PROMPT_VERSION}) : null;
      if (cached) return {response: cached, cached: true};
      const response = await proposeRepair(request);
      await service.savePaperLintRepairSuggestion(request, req.user.id, response);
      return {response, cached: false};
    });
    res.status(result.cached ? 200 : 201).json(result);
  }));

  return router;
}

module.exports = { createPaperLintRepairSuggestionRouter, ALLOWED_ROLES };
