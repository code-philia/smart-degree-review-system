const express = require('express');
const { requireAuth } = require('../auth/authMiddleware');
const { DEFAULT_NORMATIVE_RULES, analyzeDefaultNormativeRules } = require('./normativeService');
const {
  listEffectiveRuleConfigurations,
  publishRuleConfiguration,
  resetCollegeRuleConfiguration,
} = require('./ruleConfigService');
const { importRuleDraftTemplate, MAX_RULE_DRAFT_IMPORT_BYTES } = require('./ruleDraftImportService');

const router = express.Router();

function sendRuleConfigError(error, res, next) {
  if (error?.type === 'entity.too.large') {
    res.status(413).json({ code: 413, message: '文件大小不能超过 1 MB' });
    return;
  }
  if (error?.status) {
    const body = { code: error.status, message: error.message };
    if (Array.isArray(error.errors)) {
      body.errors = error.errors;
    }
    res.status(error.status).json(body);
    return;
  }
  if (error?.code === 'RULE_CONFIG_SERVICE_NOT_IMPLEMENTED' || error?.code === 'RULE_DRAFT_IMPORT_NOT_IMPLEMENTED') {
    res.status(501).json({ code: 501, message: error.message });
    return;
  }
  next(error);
}

router.get('/rules', requireAuth(), (req, res) => {
  res.json({ rules: DEFAULT_NORMATIVE_RULES });
});

router.get(
  '/rule-configs',
  requireAuth({ allowedRoles: ['SCHOOL_ADMIN', 'COLLEGE_ADMIN'] }),
  async (req, res, next) => {
    try {
      const scope = {
        level: typeof req.query?.level === 'string' ? req.query.level : undefined,
        college_id: typeof req.query?.college_id === 'string' ? req.query.college_id : undefined,
      };
      const result = await listEffectiveRuleConfigurations(req.user, scope);
      res.json(result);
    } catch (error) {
      sendRuleConfigError(error, res, next);
    }
  },
);

router.put(
  '/rule-configs',
  requireAuth({ allowedRoles: ['SCHOOL_ADMIN', 'COLLEGE_ADMIN'] }),
  async (req, res, next) => {
    try {
      const result = await publishRuleConfiguration(req.user, req.body || {});
      res.json(result);
    } catch (error) {
      sendRuleConfigError(error, res, next);
    }
  },
);

router.post(
  '/rule-configs/reset-college',
  requireAuth({ allowedRoles: ['SCHOOL_ADMIN', 'COLLEGE_ADMIN'] }),
  async (req, res, next) => {
    try {
      const result = await resetCollegeRuleConfiguration(req.user, req.body || {});
      res.json(result);
    } catch (error) {
      sendRuleConfigError(error, res, next);
    }
  },
);

router.post(
  '/rule-drafts/import',
  requireAuth({ allowedRoles: ['SCHOOL_ADMIN', 'COLLEGE_ADMIN'] }),
  express.raw({ type: ['application/json', 'application/octet-stream'], limit: MAX_RULE_DRAFT_IMPORT_BYTES }),
  async (req, res, next) => {
    try {
      const result = await importRuleDraftTemplate(req.user, {
        content: Buffer.isBuffer(req.body) ? req.body : Buffer.from(JSON.stringify(req.body || [])),
        contentType: req.get('content-type') || '',
        fileName: typeof req.query?.file_name === 'string' ? req.query.file_name : undefined,
      });
      res.status(201).json(result);
    } catch (error) {
      sendRuleConfigError(error, res, next);
    }
  },
);

router.post('/analyze', requireAuth(), async (req, res, next) => {
  try {
    const text = typeof req.body?.text === 'string' ? req.body.text : '';

    if (!text.trim()) {
      res.status(400).json({ code: 400, message: '文本不能为空' });
      return;
    }

    const result = await analyzeDefaultNormativeRules(text);
    res.json(result);
  } catch (error) {
    if (error?.code === 'NORMATIVE_RULES_NOT_IMPLEMENTED') {
      res.status(501).json({ code: 501, message: error.message });
      return;
    }
    next(error);
  }
});

module.exports = router;
