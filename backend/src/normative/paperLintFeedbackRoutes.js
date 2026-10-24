const express = require('express');
const { requireAuth } = require('../auth/authMiddleware');
const service = require('./paperLintFeedbackService');

function handler(work) {
  return async (req, res, next) => {
    try { await work(req, res); } catch (error) {
      if (error.status) res.status(error.status).json({ code: error.status, message: error.message });
      else next(error);
    }
  };
}

function findingValues(req) {
  return { reportId: req.params.reportId, userId: req.user.id, ruleId: req.params.ruleId, findingId: req.params.findingId };
}

function feedbackRouter() {
  const router = express.Router();
  router.use(requireAuth());
  router.get('/reports/:reportId/findings/:ruleId/:findingId/feedback', handler(async (req, res) => {
    res.json({ feedback: await service.getFindingFeedback(findingValues(req)) });
  }));
  router.put('/reports/:reportId/findings/:ruleId/:findingId/feedback', express.json({ limit: '8kb' }), handler(async (req, res) => {
    res.json({ feedback: await service.saveFindingFeedback({ ...findingValues(req), input: req.body || {} }) });
  }));
  router.delete('/reports/:reportId/findings/:ruleId/:findingId/feedback', handler(async (req, res) => {
    await service.deleteFindingFeedback(findingValues(req));
    res.status(204).end();
  }));
  router.get('/reports/:reportId/repair-suggestions/:suggestionId/feedback', handler(async (req, res) => {
    res.json({ feedback: await service.getSuggestionFeedback({ reportId: req.params.reportId, userId: req.user.id, suggestionId: req.params.suggestionId }) });
  }));
  router.put('/reports/:reportId/repair-suggestions/:suggestionId/feedback', express.json({ limit: '8kb' }), handler(async (req, res) => {
    res.json({ feedback: await service.saveSuggestionFeedback({ reportId: req.params.reportId, userId: req.user.id, suggestionId: req.params.suggestionId, input: req.body || {} }) });
  }));
  router.delete('/reports/:reportId/repair-suggestions/:suggestionId/feedback', handler(async (req, res) => {
    await service.deleteSuggestionFeedback({ reportId: req.params.reportId, userId: req.user.id, suggestionId: req.params.suggestionId });
    res.status(204).end();
  }));
  router.post('/system-feedback', express.json({ limit: '8kb' }), handler(async (req, res) => {
    res.status(201).json(await service.saveSystemFeedback({ userId: req.user.id, input: req.body || {} }));
  }));
  return router;
}

module.exports = { feedbackRouter };
