const { analyzeDefaultNormativeRules } = require('./normativeService');
const { resolveRulesForAnalysis } = require('./ruleConfigService');
const detectionTaskRepository = require('./detectionTaskRepository');

const MAX_DETECTION_TEXT_BYTES = 5 * 1024 * 1024;
const ALLOWED_DETECTION_FILE_EXTENSIONS = Object.freeze(['.txt', '.md']);
const DETECTION_STATUSES = Object.freeze(['pending', 'running', 'completed']);

function createHttpError(status, message) {
  const error = new Error(message);
  error.status = status;
  return error;
}

async function createDetectionTask(user, payload = {}) {
  if (!user) {
    throw createHttpError(401, '请先登录后发起规范检测');
  }

  const text = typeof payload.text === 'string' ? payload.text : '';
  if (!text.trim()) {
    throw createHttpError(400, '检测文本不能为空');
  }

  const sourceType = payload.source_type === 'file' ? 'file' : 'paste';
  const sourceFilename = typeof payload.source_filename === 'string' ? payload.source_filename : null;
  const rules = await resolveRulesForAnalysis({ college_id: user.collegeId });
  const analysis = await analyzeDefaultNormativeRules(text);
  const severityCounts = analysis.issues.reduce((counts, issue) => {
    counts[issue.severity] = (counts[issue.severity] || 0) + 1;
    return counts;
  }, {});

  return detectionTaskRepository.createDetectionTask({
    user_id: user.id,
    status: 'completed',
    source_type: sourceType,
    source_filename: sourceFilename,
    original_text: text,
    rule_snapshot: rules,
    issues: analysis.issues,
    severity_counts: severityCounts,
  });
}

module.exports = {
  MAX_DETECTION_TEXT_BYTES,
  ALLOWED_DETECTION_FILE_EXTENSIONS,
  DETECTION_STATUSES,
  createDetectionTask,
};
