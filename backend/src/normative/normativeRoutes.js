const express = require('express');
const { requireAuth } = require('../auth/authMiddleware');
const { DEFAULT_NORMATIVE_RULES, analyzeDefaultNormativeRules } = require('./normativeService');
const {
  listEffectiveRuleConfigurations,
  publishRuleConfiguration,
  resetCollegeRuleConfiguration,
} = require('./ruleConfigService');
const { importRuleDraftTemplate, MAX_RULE_DRAFT_IMPORT_BYTES } = require('./ruleDraftImportService');
const {
  createDetectionTask,
  MAX_DETECTION_TEXT_BYTES,
} = require('./detectionTaskService');
const {
  buildDownloadReportPayload,
  getDetectionReportForUser,
  listDetectionReportsForUser,
} = require('./detectionReportService');
const {
  MAX_CORPUS_SAMPLE_BYTES,
  createDuplicationCorpusSample,
  deleteDuplicationCorpusSample,
  listDuplicationCorpusSamples,
} = require('./duplicationCorpusService');
const {
  ALLOWED_DUPLICATION_DETECTION_ROLES,
  MAX_DUPLICATION_DETECTION_TEXT_BYTES,
  runDuplicationDetection,
} = require('./duplicationDetectionService');
const {
  ALLOWED_DUPLICATION_HISTORY_ROLES,
  buildDuplicationDownloadPayload,
  createDuplicationHistoryFromDetection,
  getDuplicationReportForUser,
  listDuplicationHistoryForUser,
} = require('./duplicationHistoryService');
const {
  ALLOWED_WHOLE_POLISH_ROLES,
  MAX_WHOLE_POLISH_TEXT_BYTES,
  buildDownloadText,
  createWholePolishResult,
  getWholePolishResultForUser,
} = require('./wholePolishService');
const {
  ALLOWED_LOCAL_POLISH_ROLES,
  MAX_LOCAL_POLISH_TEXT_BYTES,
  createLocalPolishResult,
  getLocalPolishResultForUser,
} = require('./localPolishService');
const {
  ALLOWED_POLISH_HISTORY_ROLES,
  buildPolishResultText,
  getPolishHistoryRecordForUser,
  listPolishHistoryForUser,
} = require('./polishHistoryService');
const {
  ALLOWED_INNOVATION_SCORING_ROLES,
  MAX_INNOVATION_SCORING_JSON_BYTES,
  calculateInnovationScore,
} = require('./innovationScoringService');
const {
  ALLOWED_INNOVATION_ASSESSMENT_ROLES,
  MAX_INNOVATION_ASSESSMENT_JSON_BYTES,
  createInnovationAssessment,
} = require('./innovationAssessmentService');
const {
  ALLOWED_INNOVATION_REPORT_ROLES,
  buildInnovationReportDownloadPayload,
  getInnovationReportForUser,
} = require('./innovationReportService');
const {
  ALLOWED_INNOVATION_HISTORY_ROLES,
  listInnovationHistoryForUser,
} = require('./innovationHistoryService');
const {
  REVIEW_RUBRIC_ALLOWED_ROLES,
  listReviewRubrics,
} = require('./reviewRubricService');
const {
  ALLOWED_AI_REVIEW_RUN_ROLES,
  MAX_AI_REVIEW_TEXT_BYTES,
  createAiReviewRun,
} = require('./aiReviewRunService');
const {
  ALLOWED_AI_REVIEW_RESULT_ROLES,
  buildAiReviewResultDownloadPayload,
  getAiReviewResultForUser,
} = require('./aiReviewResultService');
const {
  ALLOWED_AI_REVIEW_HISTORY_ROLES,
  listAiReviewHistoryForUser,
} = require('./aiReviewHistoryService');
const ledgerRecordsRoutes = require('./ledgerRecordsRoutes');
const reportSubmissionRoutes = require('./reportSubmissionRoutes');
const reportSupervisorQueueRoutes = require('./reportSupervisorQueueRoutes');
const reportStudentResultsRoutes = require('./reportStudentResultsRoutes');

const router = express.Router();

router.use('/ledger-records', ledgerRecordsRoutes);
router.use('/report-submissions', reportSubmissionRoutes);
router.use('/supervisor-review-queue', reportSupervisorQueueRoutes);
router.use('/student-report-results', reportStudentResultsRoutes);

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

router.get('/review-rubrics', requireAuth({ allowedRoles: REVIEW_RUBRIC_ALLOWED_ROLES }), (req, res) => {
  res.json(listReviewRubrics());
});

router.get(
  '/duplication-corpus',
  requireAuth({ allowedRoles: ['SCHOOL_ADMIN'] }),
  async (req, res, next) => {
    try {
      const samples = await listDuplicationCorpusSamples(req.user);
      res.json({ samples });
    } catch (error) {
      if (error?.status) {
        res.status(error.status).json({ code: error.status, message: error.message });
        return;
      }
      next(error);
    }
  },
);

router.post(
  '/duplication-corpus',
  requireAuth({ allowedRoles: ['SCHOOL_ADMIN'] }),
  express.json({ limit: MAX_CORPUS_SAMPLE_BYTES }),
  async (req, res, next) => {
    try {
      const sample = await createDuplicationCorpusSample(req.user, req.body || {});
      res.status(201).json(sample);
    } catch (error) {
      if (error?.type === 'entity.too.large') {
        res.status(413).json({ code: 413, message: '样本文本不能超过 5 MB' });
        return;
      }
      if (error?.status) {
        res.status(error.status).json({ code: error.status, message: error.message });
        return;
      }
      next(error);
    }
  },
);

router.delete(
  '/duplication-corpus/:sampleId',
  requireAuth({ allowedRoles: ['SCHOOL_ADMIN'] }),
  async (req, res, next) => {
    try {
      await deleteDuplicationCorpusSample(req.user, req.params.sampleId);
      res.status(204).send();
    } catch (error) {
      if (error?.status) {
        res.status(error.status).json({ code: error.status, message: error.message });
        return;
      }
      next(error);
    }
  },
);

router.post(
  '/duplication-detections',
  requireAuth({ allowedRoles: ALLOWED_DUPLICATION_DETECTION_ROLES }),
  express.json({ limit: MAX_DUPLICATION_DETECTION_TEXT_BYTES }),
  async (req, res, next) => {
    try {
      const payload = req.body || {};
      const result = await runDuplicationDetection(req.user, payload);
      if (result.status === 'completed') {
        await createDuplicationHistoryFromDetection(req.user, payload, result);
      }
      res.status(201).json(result);
    } catch (error) {
      if (error?.type === 'entity.too.large') {
        res.status(413).json({ code: 413, message: '待检文本不能超过 5 MB' });
        return;
      }
      if (error?.status) {
        res.status(error.status).json({ code: error.status, message: error.message });
        return;
      }
      next(error);
    }
  },
);

router.get(
  '/duplication-detection-reports',
  requireAuth({ allowedRoles: ALLOWED_DUPLICATION_HISTORY_ROLES }),
  async (req, res, next) => {
    try {
      const records = await listDuplicationHistoryForUser(req.user);
      res.json({ records });
    } catch (error) {
      if (error?.status) {
        res.status(error.status).json({ code: error.status, message: error.message });
        return;
      }
      next(error);
    }
  },
);

router.get(
  '/duplication-detection-reports/:reportId',
  requireAuth({ allowedRoles: ALLOWED_DUPLICATION_HISTORY_ROLES }),
  async (req, res, next) => {
    try {
      const report = await getDuplicationReportForUser(req.user, req.params.reportId);
      res.json(report);
    } catch (error) {
      if (error?.status) {
        res.status(error.status).json({ code: error.status, message: error.message });
        return;
      }
      next(error);
    }
  },
);

router.get(
  '/duplication-detection-reports/:reportId/download',
  requireAuth({ allowedRoles: ALLOWED_DUPLICATION_HISTORY_ROLES }),
  async (req, res, next) => {
    try {
      const report = await getDuplicationReportForUser(req.user, req.params.reportId);
      res
        .type('application/json; charset=utf-8')
        .attachment(`duplication-report-${report.id}.json`)
        .send(JSON.stringify(buildDuplicationDownloadPayload(report), null, 2));
    } catch (error) {
      if (error?.status) {
        res.status(error.status).json({ code: error.status, message: error.message });
        return;
      }
      next(error);
    }
  },
);

router.post(
  '/whole-polish-results',
  requireAuth({ allowedRoles: ALLOWED_WHOLE_POLISH_ROLES }),
  express.json({ limit: MAX_WHOLE_POLISH_TEXT_BYTES }),
  async (req, res, next) => {
    try {
      const result = await createWholePolishResult(req.user, req.body || {});
      res.status(201).json(result);
    } catch (error) {
      if (error?.type === 'entity.too.large') {
        res.status(413).json({ code: 413, message: '文件或文本不能超过 5 MB' });
        return;
      }
      if (error?.status) {
        res.status(error.status).json({ code: error.status, message: error.message });
        return;
      }
      next(error);
    }
  },
);

router.get(
  '/whole-polish-results/:resultId',
  requireAuth({ allowedRoles: ALLOWED_WHOLE_POLISH_ROLES }),
  async (req, res, next) => {
    try {
      const result = await getWholePolishResultForUser(req.user, req.params.resultId);
      res.json(result);
    } catch (error) {
      if (error?.status) {
        res.status(error.status).json({ code: error.status, message: error.message });
        return;
      }
      next(error);
    }
  },
);

router.get(
  '/whole-polish-results/:resultId/download',
  requireAuth({ allowedRoles: ALLOWED_WHOLE_POLISH_ROLES }),
  async (req, res, next) => {
    try {
      const result = await getWholePolishResultForUser(req.user, req.params.resultId);
      res
        .type('text/plain; charset=utf-8')
        .attachment(`whole-polish-${result.id}.txt`)
        .send(buildDownloadText(result));
    } catch (error) {
      if (error?.status) {
        res.status(error.status).json({ code: error.status, message: error.message });
        return;
      }
      next(error);
    }
  },
);

router.post(
  '/local-polish-results',
  requireAuth({ allowedRoles: ALLOWED_LOCAL_POLISH_ROLES }),
  express.json({ limit: MAX_LOCAL_POLISH_TEXT_BYTES }),
  async (req, res, next) => {
    try {
      const result = await createLocalPolishResult(req.user, req.body || {});
      res.status(201).json(result);
    } catch (error) {
      if (error?.type === 'entity.too.large') {
        res.status(413).json({ code: 413, message: '局部润色文本不能超过 5 MB' });
        return;
      }
      if (error?.status) {
        res.status(error.status).json({ code: error.status, message: error.message });
        return;
      }
      if (error?.code === 'LOCAL_POLISH_SERVICE_NOT_IMPLEMENTED') {
        res.status(501).json({ code: 501, message: error.message });
        return;
      }
      next(error);
    }
  },
);

router.get(
  '/local-polish-results/:resultId',
  requireAuth({ allowedRoles: ALLOWED_LOCAL_POLISH_ROLES }),
  async (req, res, next) => {
    try {
      const result = await getLocalPolishResultForUser(req.user, req.params.resultId);
      res.json(result);
    } catch (error) {
      if (error?.status) {
        res.status(error.status).json({ code: error.status, message: error.message });
        return;
      }
      next(error);
    }
  },
);

router.get(
  '/polish-history',
  requireAuth({ allowedRoles: ALLOWED_POLISH_HISTORY_ROLES }),
  async (req, res, next) => {
    try {
      const records = await listPolishHistoryForUser(req.user);
      res.json({ records });
    } catch (error) {
      if (error?.status) {
        res.status(error.status).json({ code: error.status, message: error.message });
        return;
      }
      next(error);
    }
  },
);

router.get(
  '/polish-history/:polishType/:resultId/download',
  requireAuth({ allowedRoles: ALLOWED_POLISH_HISTORY_ROLES }),
  async (req, res, next) => {
    try {
      const record = await getPolishHistoryRecordForUser(req.user, req.params.polishType, req.params.resultId);
      res
        .type('text/plain; charset=utf-8')
        .attachment(`polish-result-${record.polish_type}-${record.id}.txt`)
        .send(buildPolishResultText(record));
    } catch (error) {
      if (error?.status) {
        res.status(error.status).json({ code: error.status, message: error.message });
        return;
      }
      next(error);
    }
  },
);

router.get(
  '/polish-history/:polishType/:resultId',
  requireAuth({ allowedRoles: ALLOWED_POLISH_HISTORY_ROLES }),
  async (req, res, next) => {
    try {
      const record = await getPolishHistoryRecordForUser(req.user, req.params.polishType, req.params.resultId);
      res.json(record);
    } catch (error) {
      if (error?.status) {
        res.status(error.status).json({ code: error.status, message: error.message });
        return;
      }
      next(error);
    }
  },
);

router.post(
  '/innovation-scores',
  requireAuth({ allowedRoles: ALLOWED_INNOVATION_SCORING_ROLES }),
  express.json({ limit: MAX_INNOVATION_SCORING_JSON_BYTES }),
  async (req, res, next) => {
    try {
      const result = await calculateInnovationScore(req.user, req.body || {});
      res.status(201).json(result);
    } catch (error) {
      if (error?.type === 'entity.too.large') {
        res.status(413).json({ code: 413, message: '评分输入不能超过 32 KB' });
        return;
      }
      if (error?.status) {
        res.status(error.status).json({ code: error.status, message: error.message });
        return;
      }
      if (error?.code === 'INNOVATION_SCORING_SERVICE_NOT_IMPLEMENTED') {
        res.status(501).json({ code: 501, message: error.message });
        return;
      }
      next(error);
    }
  },
);

router.post(
  '/innovation-assessments',
  requireAuth({ allowedRoles: ALLOWED_INNOVATION_ASSESSMENT_ROLES }),
  express.json({ limit: MAX_INNOVATION_ASSESSMENT_JSON_BYTES }),
  async (req, res, next) => {
    try {
      const result = await createInnovationAssessment(req.user, req.body || {});
      res.status(201).json(result);
    } catch (error) {
      if (error?.type === 'entity.too.large') {
        res.status(413).json({ code: 413, message: '评估输入不能超过 32 KB' });
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
      next(error);
    }
  },
);

router.post(
  '/ai-review-runs',
  requireAuth({ allowedRoles: ALLOWED_AI_REVIEW_RUN_ROLES }),
  express.json({ limit: MAX_AI_REVIEW_TEXT_BYTES }),
  async (req, res, next) => {
    try {
      const result = await createAiReviewRun(req.user, req.body || {});
      res.status(201).json(result);
    } catch (error) {
      if (error?.type === 'entity.too.large') {
        res.status(413).json({ code: 413, message: '论文文本不能超过 5 MB' });
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
      next(error);
    }
  },
);

router.get(
  '/ai-review-runs/:reviewRunId',
  requireAuth({ allowedRoles: ALLOWED_AI_REVIEW_RESULT_ROLES }),
  async (req, res, next) => {
    try {
      const result = await getAiReviewResultForUser(req.user, req.params.reviewRunId);
      res.json(result);
    } catch (error) {
      if (error?.status) {
        res.status(error.status).json({ code: error.status, message: error.message });
        return;
      }
      next(error);
    }
  },
);

router.get(
  '/ai-review-runs',
  requireAuth({ allowedRoles: ALLOWED_AI_REVIEW_HISTORY_ROLES }),
  async (req, res, next) => {
    try {
      const records = await listAiReviewHistoryForUser(req.user);
      res.json({ records });
    } catch (error) {
      if (error?.status) {
        res.status(error.status).json({ code: error.status, message: error.message });
        return;
      }
      next(error);
    }
  },
);

router.get(
  '/ai-review-runs/:reviewRunId/download',
  requireAuth({ allowedRoles: ALLOWED_AI_REVIEW_RESULT_ROLES }),
  async (req, res, next) => {
    try {
      const result = await getAiReviewResultForUser(req.user, req.params.reviewRunId);
      res
        .type('application/json; charset=utf-8')
        .attachment(`ai-review-result-${result.id}.json`)
        .send(JSON.stringify(buildAiReviewResultDownloadPayload(result), null, 2));
    } catch (error) {
      if (error?.status) {
        res.status(error.status).json({ code: error.status, message: error.message });
        return;
      }
      next(error);
    }
  },
);

router.get(
  '/innovation-assessments',
  requireAuth({ allowedRoles: ALLOWED_INNOVATION_HISTORY_ROLES }),
  async (req, res, next) => {
    try {
      const records = await listInnovationHistoryForUser(req.user);
      res.json({ records });
    } catch (error) {
      if (error?.status) {
        res.status(error.status).json({ code: error.status, message: error.message });
        return;
      }
      next(error);
    }
  },
);

router.get(
  '/innovation-assessments/:reportId',
  requireAuth({ allowedRoles: ALLOWED_INNOVATION_REPORT_ROLES }),
  async (req, res, next) => {
    try {
      const report = await getInnovationReportForUser(req.user, req.params.reportId);
      res.json(report);
    } catch (error) {
      if (error?.status) {
        res.status(error.status).json({ code: error.status, message: error.message });
        return;
      }
      next(error);
    }
  },
);

router.get(
  '/innovation-assessments/:reportId/download',
  requireAuth({ allowedRoles: ALLOWED_INNOVATION_REPORT_ROLES }),
  async (req, res, next) => {
    try {
      const report = await getInnovationReportForUser(req.user, req.params.reportId);
      res
        .type('application/json; charset=utf-8')
        .attachment(`innovation-report-${report.id}.json`)
        .send(JSON.stringify(buildInnovationReportDownloadPayload(report), null, 2));
    } catch (error) {
      if (error?.status) {
        res.status(error.status).json({ code: error.status, message: error.message });
        return;
      }
      next(error);
    }
  },
);

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

router.get(
  '/detection-reports',
  requireAuth({ allowedRoles: ['STUDENT', 'SUPERVISOR', 'SCHOOL_ADMIN', 'COLLEGE_ADMIN'] }),
  async (req, res, next) => {
    try {
      const records = await listDetectionReportsForUser(req.user);
      res.json({ records });
    } catch (error) {
      if (error?.status) {
        res.status(error.status).json({ code: error.status, message: error.message });
        return;
      }
      next(error);
    }
  },
);

router.get(
  '/detection-reports/:taskId',
  requireAuth({ allowedRoles: ['STUDENT', 'SUPERVISOR', 'SCHOOL_ADMIN', 'COLLEGE_ADMIN'] }),
  async (req, res, next) => {
    try {
      const report = await getDetectionReportForUser(req.user, req.params.taskId);
      res.json(report);
    } catch (error) {
      if (error?.status) {
        res.status(error.status).json({ code: error.status, message: error.message });
        return;
      }
      next(error);
    }
  },
);

router.get(
  '/detection-reports/:taskId/download',
  requireAuth({ allowedRoles: ['STUDENT', 'SUPERVISOR', 'SCHOOL_ADMIN', 'COLLEGE_ADMIN'] }),
  async (req, res, next) => {
    try {
      const report = await getDetectionReportForUser(req.user, req.params.taskId);
      res
        .type('application/json; charset=utf-8')
        .attachment(`normative-report-${report.id}.json`)
        .send(JSON.stringify(buildDownloadReportPayload(report), null, 2));
    } catch (error) {
      if (error?.status) {
        res.status(error.status).json({ code: error.status, message: error.message });
        return;
      }
      next(error);
    }
  },
);

router.post(
  '/detection-tasks',
  requireAuth({ allowedRoles: ['STUDENT', 'SUPERVISOR', 'SCHOOL_ADMIN', 'COLLEGE_ADMIN'] }),
  express.json({ limit: MAX_DETECTION_TEXT_BYTES }),
  async (req, res, next) => {
    try {
      const result = await createDetectionTask(req.user, req.body || {});
      res.status(201).json(result);
    } catch (error) {
      if (error?.type === 'entity.too.large') {
        res.status(413).json({ code: 413, message: '文件或文本不能超过 5 MB' });
        return;
      }
      if (error?.status) {
        res.status(error.status).json({ code: error.status, message: error.message });
        return;
      }
      next(error);
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
