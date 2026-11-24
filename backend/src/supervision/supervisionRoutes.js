const express = require('express');
const { requireAuth, parseCookies } = require('../auth/authMiddleware');
const { SESSION_COOKIE_NAME } = require('../auth/sessionService');
const { supervisionSessionAllowed } = require('../auth/supervisionPolicy');
const repository = require('./supervisionRepository');
const { sendPrivatePdf } = require('../normative/privatePdfResponse');
const { getPaperLintCatalog } = require('../normative/reviewPilotPaperLintService');

const router = express.Router();
router.use((_req, res, next) => { res.set('Cache-Control', 'private, no-store'); next(); });
router.use(requireAuth({ allowedRoles: ['SCHOOL_ADMIN'], allowSupervision: true }));
router.use((req, res, next) => {
  if (!supervisionSessionAllowed(req.user, parseCookies(req.headers.cookie)[SESSION_COOKIE_NAME])) {
    return res.status(403).json({ code: 403, message: '仅监管管理员可查看此页面' });
  }
  return next();
});
function handler(work) {
  return async (req, res, next) => {
    try { await work(req, res, next); }
    catch (error) { if (error.status) res.status(error.status).json({ code: error.status, message: error.message }); else next(error); }
  };
}
router.get('/summary', handler(async (_req, res) => res.json(await repository.summary())));
router.get('/reports', handler(async (req, res) => res.json(await repository.listReports(req.query))));
router.get('/feedback', handler(async (req, res) => res.json(await repository.listFeedback(req.query))));
router.get('/rules', handler(async (_req, res) => {
  const catalog = await getPaperLintCatalog({ mvpOnly: false });
  res.json({ rules: catalog.rules.map(({ rule_id, title, description, default_severity, default_enabled, execution_mode, uses_external_model, available }) =>
    ({ rule_id, title, description, default_severity, default_enabled, execution_mode, uses_external_model, available, repair_supported: false })) });
}));
router.get('/reports/:reportId/pdf', handler(async (req, res, next) => {
  const pdf = await repository.reportPdf(req.params.reportId, req.query.type);
  if (!pdf) return res.status(404).json({ code: 404, message: '未找到该审查报告' });
  if (!pdf.path) return res.status(410).json({ code: 410, message: '该报告的原始 PDF 已不可用' });
  await sendPrivatePdf(req, res, pdf.path, pdf.source_filename, next);
}));
router.get('/reports/:reportId', handler(async (req, res) => {
  const result = await repository.reportDetail(req.params.reportId, req.query.type);
  if (!result) return res.status(404).json({ code: 404, message: '未找到该审查报告' });
  return res.json(result);
}));
module.exports = router;
