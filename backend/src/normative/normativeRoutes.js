const express = require('express');
const { requireAuth } = require('../auth/authMiddleware');
const { DEFAULT_NORMATIVE_RULES, analyzeDefaultNormativeRules } = require('./normativeService');
const {
  listEffectiveRuleConfigurations,
  publishRuleConfiguration,
  resetCollegeRuleConfiguration,
} = require('./ruleConfigService');

const router = express.Router();

function sendRuleConfigError(error, res, next) {
  if (error?.status) {
    res.status(error.status).json({ code: error.status, message: error.message });
    return;
  }
  if (error?.code === 'RULE_CONFIG_SERVICE_NOT_IMPLEMENTED') {
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
