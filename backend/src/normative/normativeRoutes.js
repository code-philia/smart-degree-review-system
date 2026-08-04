const express = require('express');
const { requireAuth } = require('../auth/authMiddleware');
const { DEFAULT_NORMATIVE_RULES, analyzeDefaultNormativeRules } = require('./normativeService');

const router = express.Router();

router.get('/rules', requireAuth(), (req, res) => {
  res.json({ rules: DEFAULT_NORMATIVE_RULES });
});

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
